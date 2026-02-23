"""
Created on 20.06.2015

@author: skaufmann


Module containing the ScanParameters dictionaries as needed for Scanning with the standard Sequencers
"""

from copy import deepcopy
from datetime import datetime

from Tilda.Driver.DataAcquisitionFpga.TriggerTypes import TriggerTypes as TiTs
from Tilda.Driver.DataAcquisitionFpga.ScanDeviceTypes import ScanDeviceTypes as ScTypes
from Tilda.PolliFit.Measurement.SpecData import SpecDataXAxisUnits as Units


""" List of currently supported sequencer types """

sequencer_types_list = ['cs', 'trs', 'csdummy', 'trsdummy', 'kepco']

""" List of currently supported scan device classes """

scan_dev_classes_available = [sc_t.name for sc_t in ScTypes]

""" dict of currently supported DAC types and names """

dac_type_list = ['AD57X1']

""" outer most dictionary contains the following keys: """

scanDict_list = ['isotopeData', 'track0', 'pipeInternals']

""" the isotopeData dictionary is used for the whole isotope and contains the following keys: """

isotopeData_list = ['version', 'type', 'isotope', 'nOfTracks', 'accVolt', 'laserFreq']

""" the pipeInternals dictionary is used by the pipeline and is in first place only valid for one track.
It contains the following keys: """

pipeInternals_list = ['curVoltInd', 'activeTrackNumber', 'workingDirectory', 'activeXmlFilePath']

""" the measureVoltPars dictionary is used to define the pulse length to start the voltage measurement
 and the timeout of the voltage measurement. It contains the following keys: """

measureVoltPars_list = ['preScan', 'duringScan', 'postScan']
# measureVoltPars_list = ['measVoltPulseLength25ns', 'measVoltTimeout10ns']

""" list of default triton/SQL pars: """
triton_list = ['preScan', 'duringScan', 'postScan']
sql_list = ['preScan', 'duringScan', 'postScan']


""" the track0 dictionary is only used by one track but therefore beholds
the most information for the sequencer. It contains the following keys and
MUST be appended with the keys from the corresponding sequencer (see below): """

track0_list = ['nOfSteps', 'nOfScans', 'nOfCompletedSteps',
               'invertScan', 'postAccOffsetVoltControl', 'postAccOffsetVolt', 'waitForKepco1us',
               'waitAfterReset1us', 'activePmtList', 'colDirTrue', 'workingTime', 'trigger', 'pulsePattern',
               'measureVoltPars', 'triton', 'sql', 'outbits', 'scanDevice']

"""  each sequencer needs its own parameters and therefore, the keys are listed below
naming convention is type_list.  """

cs_list = ['dwellTime10ns']

trs_list = ['nOfBins', 'nOfBunches', 'softwGates', 'softBinWidth_ns', 'step_trigger']

kepco_list = []

csdummy_list = cs_list

trsdummy_list = trs_list

""" below are some example values which can be used for scanning: """

draftIsotopePars = {
    'version': '1.06', 'type': 'trs', 'isotope': '40_Ca',
    'nOfTracks': 1, 'accVolt': 9999.8,
    'laserFreq': 12568.766,
    'isotopeStartTime': datetime.today().strftime('%Y-%m-%d %H:%M:%S')
}

draftMeasureVoltPars_singl = {'measVoltPulseLength25ns': 400, 'measVoltTimeout10ns': 1000000000,
                              'dmms': {}, 'switchBoxSettleTimeS': 2.0, 'measurementCompleteDestination': 'software'}
draftMeasureVoltPars = {'preScan': deepcopy(draftMeasureVoltPars_singl),
                        'duringScan': deepcopy(draftMeasureVoltPars_singl),
                        'postScan': deepcopy(draftMeasureVoltPars_singl)}

draftPipeInternals = {
    'curVoltInd': 0,
    'activeTrackNumber': (0, 'track0'),
    'workingDirectory': None,
    'activeXmlFilePath': 'c:\\'
}

draft_triton_pars_singl = {'dummyDev': {
    'calls': {'required': 2, 'data': [], 'acquired': 0},
    'random': {'required': 4, 'data': [], 'acquired': 0}}}

draft_triton_pars = {
    # 'preScan': deepcopy(draft_triton_pars_singl),
    # 'postScan': deepcopy(draft_triton_pars_singl),
    'preScan': {},
    'duringScan': {},
    'postScan': {},
}

draft_sql_pars = {
    'preScan': {},
    'duringScan': {},
    'postScan': {},
}

draft_outbits = {
    'outbit0': [('toggle', 'scan', 0)],
    'outbit1': [('on', 'step', 1), ('off', 'step', 5)],
    'outbit2': [('on', 'step', 1), ('off', 'step', 5)]
}

# this must always be present by a scan device:
# leave this as it is since this will be called for old track dict which do not have this yet!
draft_scan_device = {
    'name': 'AD5781_Ser1',
    'type': 'AD57X1(DAC)',  # what type of device, e.g. AD5781(DAC) / Matisse (laser)
    'devClass': 'DAC',  # carrier class of the dev, e.g. DAC / Triton
    'stepUnitName': Units.line_volts.name,  # name if the SpecDataXAxisUnits
    'start': 0.0,  # in units of stepUnitName
    'stepSize': 1.0,  # in units of stepUnitName
    'stop': 5.0,  # in units of stepUnitName
    'preScanSetPoint': None,  # in units of stepUnitName, choose None if nothing should happen
    'postScanSetPoint': None,  # in units of stepUnitName, choose None if nothing should happen
    'timeout_s': 10.0,  # timeout in seconds after which step setting is accounted as failure due to timeout,
    # set top 0 for never timing out.
    'setValLimit': (-15.0, 15.0),
    'stepSizeLimit': (7.628880920000002e-05, 15.0)
}

scan_dev_keys_list = ['name', 'type', 'devClass', 'stepUnitName', 'start', 'stepSize', 'stop',
                      'preScanSetPoint', 'postScanSetPoint', 'timeout_s']

draft_trigger_pars = {'meas_trigger': {'type': getattr(TiTs, 'no_trigger')},
                      'step_trigger': {'type': getattr(TiTs, 'no_trigger')},
                      'scan_trigger': {'type': getattr(TiTs, 'no_trigger')}}

draftTrackPars = {
    'nOfSteps': 100, 'nOfScans': 2,  # also relevant for scan but not specific for the type of scan dev
    'nOfCompletedSteps': 0, 'invertScan': False,  # also relevant for scan but not specific for the type of scan dev
    'postAccOffsetVoltControl': 0, 'postAccOffsetVolt': 0,
    'waitForKepco1us': 100,
    'waitAfterReset1us': 500,
    'activePmtList': [0, 1],
    'colDirTrue': False,
    'dwellTime10ns': 2000000,
    'workingTime': None,
    'nOfBins': 1000,
    'softBinWidth_ns': 100,
    'nOfBunches': 1,
    'softwGates': [[-10, 10, 0, 10000], [-10, 10, 0, 10000]],
    'trigger': draft_trigger_pars,
    'pulsePattern': {'cmdList': ['$time::1.0::1::0', '$time::1.0::0::0']},
    'measureVoltPars': draftMeasureVoltPars,
    'triton': draft_triton_pars,
    'sql': draft_sql_pars,
    'outbits': draft_outbits,
    'scanDevice': draft_scan_device
}

draftScanDict = {
    'isotopeData': draftIsotopePars,
    'track0': draftTrackPars,
    'pipeInternals': draftPipeInternals
}

# for the time resolved sequencer us this:
# draftTrackPars = {'MCSSelectTrigger': 0, 'delayticks': 0, 'nOfBins': 10000, 'nOfBunches': 1,
# 'measVoltPulseLength25ns': 400, 'measVoltTimeout10ns': 100,
# 'VoltOrScaler': False, 'dacStepSize18Bit': int('00000010000000000000', 2),
# 'dacStartRegister18Bit': int('00000000001000000000', 2), 'nOfSteps': 20,
# 'nOfScans': 30, 'nOfCompletedSteps': 0, 'invertScan': False,
# 'measureOffset': False, 'postAccOffsetVoltControl': 1, 'postAccOffsetVolt': 1000,
# 'waitForKepco1us': 40,
# 'waitAfterReset1us': 4000,
# 'activePmtList': [0, 2, 4]
# }
