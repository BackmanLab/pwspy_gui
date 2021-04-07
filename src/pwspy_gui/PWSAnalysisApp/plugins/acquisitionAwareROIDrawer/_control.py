import typing as t_

import numpy as np
from PyQt5.QtCore import QObject
from pwspy.utility.acquisition import SequencerStep, SeqAcqDir, PositionsStep, TimeStep, SequencerCoordinate
import pwspy.dataTypes as pwsdt
from pwspy_gui.PWSAnalysisApp._roiManager import ROIManager


class Options(t_.NamedTuple):
    copyAlongTime: bool
    trackMovement: bool


class SequenceController:
    """A utility class to help with selected acquisitions from a sequence that includes a multiple position and time series. both are optional"""
    def __init__(self, sequence: SequencerStep, acqs: t_.Sequence[SeqAcqDir]):
        self.sequence = sequence
        self.coordMap: t_.Dict[pwsdt.AcqDir, SequencerCoordinate] = {acq.acquisition: acq.sequencerCoordinate for acq in acqs}  # A dictionary of the sequence coords keyed by tha acquisition
        posSteps = [step for step in sequence.iterateChildren() if isinstance(step, PositionsStep)]
        assert not len(posSteps) > 1, "Sequences with more than one `MultiplePositionsStep` are not currently supported"
        timeSteps = [step for step in sequence.iterateChildren() if isinstance(step, TimeStep)]
        assert not len(timeSteps) > 1, "Sequences with more than one `TimeSeriesStep` are not currently supported"

        self.timeStep = timeSteps[0] if len(timeSteps) > 0 else None
        self.posStep = posSteps[0] if len(posSteps) > 0 else None
        self._iterSteps = (self.timeStep, self.posStep)

        self._tIndex = None
        self._pIndex = None

    def getTimeNames(self) -> t_.Optional[t_.Sequence[str]]:
        if self.timeStep is None:
            return None
        else:
            return tuple([self.timeStep.getIterationName(i) for i in range(self.timeStep.stepIterations())])

    def getPositionNames(self) -> t_.Optional[t_.Sequence[str]]:
        if self.posStep is None:
            return None
        else:
            return tuple([self.posStep.getIterationName(i) for i in range(self.posStep.stepIterations())])

    def setCoordinates(self, posIndex: t_.Optional[int], tIndex: t_.Optional[int]) -> pwsdt.AcqDir:
        acq = self.getAcquisitionForIndices(tIndex, posIndex)
        self._tIndex = tIndex
        self._pIndex = posIndex
        return acq

    def getIndicesForAcquisition(self, acq: t_.Union[SeqAcqDir, pwsdt.AcqDir]) -> t_.Tuple[int, int]:
        """Returns the iteration indices of the given acquisition in the form (timeIdx, posIdx)"""
        coord: SequencerCoordinate = acq.sequencerCoordinate if isinstance(acq, SeqAcqDir) else self.coordMap[acq]
        tIdx = coord.getStepIteration(self.timeStep) if self.timeStep is not None else None
        pIdx = coord.getStepIteration(self.posStep) if self.posStep is not None else None
        return tIdx, pIdx

    def getAcquisitionForIndices(self, tIndex: int, pIndex: int) -> pwsdt.AcqDir:
        step: SequencerStep = self._iterSteps[np.argmax([len(i.getTreePath()) if i is not None else 0 for i in self._iterSteps])]  # The step that is furthest down the tree path
        coordRange = step.getCoordinate()
        if self.timeStep is not None:
            coordRange.setAcceptedIterations(self.timeStep.id, [tIndex])
        if self.posStep is not None:
            coordRange.setAcceptedIterations(self.posStep.id, [pIndex])
        for acq, coord in self.coordMap.items():
            if coord in coordRange:
                return acq
        raise ValueError(f"No acquisition was found to match Position index: {pIndex}, Time index: {tIndex}") # If we got this far then no matching acquisition was found.

    def getCurrentIndices(self) -> t_.Tuple[int, int]:
        """Of the form (tIndex, pIndex)"""
        return self._tIndex, self._pIndex


class RoiController(QObject):
    """Handles applying ROI changes across axes.

    """
    def __init__(self, seqController: SequenceController, initialOptions: Options, roiManager: ROIManager, parent: QObject = None):
        super().__init__(parent=parent)
        self._seqController = seqController
        self._options = initialOptions
        self._roiManager = roiManager

    def setOptions(self, options: Options):
        self._options = options

    def getOptions(self) -> Options:
        return self._options

    def setRoiChanged(self, acq: pwsdt.AcqDir, roiFile: pwsdt.RoiFile, overwrite: bool):
        if not self._options.copyAlongTime:
            return
        tIdx, pIdx = self._seqController.getIndicesForAcquisition(acq)
        if tIdx is None:
            return
        for i in range(tIdx+1, self._seqController.timeStep.stepIterations()):
            acq = self._seqController.getAcquisitionForIndices(i, pIdx)
            self._roiManager.createRoi(acq, roiFile.getRoi(), roiFile.name, roiFile.number, overwrite=overwrite)

    def deleteRoi(self, acq: pwsdt.AcqDir, roiFile: pwsdt.RoiFile):
        if not self._options.copyAlongTime:
            return
        tIdx, pIdx = self._seqController.getIndicesForAcquisition(acq)
        if tIdx is None:
            return
        for i in range(tIdx+1, self._seqController.timeStep.stepIterations()):
            acq = self._seqController.getAcquisitionForIndices(i, pIdx)
            roiSpecs = [(roiName, roiNum) for roiName, roiNum, fformat in acq.getRois()]
            if (roiFile.name, roiFile.number) in roiSpecs:
                self._roiManager.removeRoi(self._roiManager.getROI(acq, roiFile.name, roiFile.number))
