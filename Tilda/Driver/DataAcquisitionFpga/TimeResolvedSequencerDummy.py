"""
Created on 

@author: simkaufm

Module Description: Dummy module for the time resolved sequencer, when there is no fpga at hand.
"""

import ctypes
from datetime import datetime
import logging

import numpy as np

import Tilda.Driver.DataAcquisitionFpga.TimeResolvedSequencerConfig as TrsCfg
import Tilda.Service.Formatting as Form
from Tilda.Driver.DataAcquisitionFpga.MeasureVolt import MeasureVolt
from Tilda.Driver.DataAcquisitionFpga.SequencerCommon import Sequencer


class TimeResolvedSequencer(Sequencer, MeasureVolt):
    def __init__(self):
        """
        Dummy TimeResolvedSequencer should behave more or less
        just like the original one but not communicate with any hardware
        """

        self.config = TrsCfg
        super(Sequencer, self).__init__(self.config.bitfilePath, self.config.bitfileSignature,
                                        self.config.fpgaResource, dummy=True)
        self.type = 'trsdummy'
        self.artificial_build_data = []
        self.scan_dev = 'DAC'  # Can use dummy with an external scan dev
        self.scan_dev_timeout = 1  # in seconds. Relevant if using external scan dev
        self.ready_for_step = False  # relevant if using external scan dev
        self.status = TrsCfg.seqStateDict['init']
        self.session = ctypes.c_ulong(0)
        self.status = 0

    '''read Indicators:'''

    def getMCSState(self):
        """
        always 0 in dummy mode
        :return:int, state of MultiChannelScaler
        """
        return 0

    def getDACQuWriteTimeout(self):
        """
        always False in dummy Mode
        :return: bool, True if timedout
        """
        return False

    def getErrorCount(self):
        """
        gets the ErrorCount which represents how many errors have occured for the MultiChannelScaler
        for example each time abort is pressed, ErrorCount is raised by 1
        :return:int, MCSerrorcount
        """
        return 0

    def getInternalDACState(self):
        """
        True in dummy mode if scandev is DAC
        :return: bool: True if DAC available
        """
        if self.scan_dev == 'DAC':
            return True
        else:
            return False

    '''set Controls'''

    def setMCSParameters(self, scanpars, track_name):
        """
        always True in dummy Mode
        """
        return True

    def setScanDeviceParameters(self, scanDevDict):
        """
        Writes the chosen scanDev type to the FPGA.
        :param scanDevDict: dict: Currently supported devices are "DAC"(0) and "Triton"(1)
        :return:
        """
        # write scan device class as int to fpga
        device_type = scanDevDict.get('devClass', 'DAC')
        if scanDevDict.get('type', '') == 'NI_USB6225_AO':
            device_type = 'Triton'
        self.scan_dev = device_type
        # write timeout in 10ns units to fpga
        timeout_s = scanDevDict.get('timeout_s', 1)  # default: 1sec = 100 000 000 * 10ns
        self.scan_dev_timeout = timeout_s

        return self.checkFpgaStatus()

    def scanDeviceReadyForStep(self, ready_bool):
        """
        Sets the "scanDevSet" bool on the FPGA. Should be used to signal when a scan device is ready for the next step.
        If implemented on the FPGA might also be used to halt the measurement when the scan device is not stable any more.
        :param ready_bool: bool: True if the scan device is ready for the next step.
        :return:
        """
        self.ready_for_step = ready_bool

    def setAllScanParameters(self, scanpars, track_num):
        """
        Use the dictionary format of act_scan_wins, to set all parameters at once.
         Therefore Sequencer must be in idle state
        :param scanpars: dictionary, containing all scanparameters
        :return: bool, True if successful
        always True in dummy Mode
        """
        track_name = 'track' + str(track_num)
        self.setScanDeviceParameters(scanpars[track_name]['scanDevice'])
        return True

    def setPostAccelerationControlState(self, desiredState, blocking=True):
        """
        will set the PostAccelerationControl State, so one can chose which PowerSupply will be used.
        :return: int, the current State of the Control Box
        """
        pass

    def getPostAccelerationControlStateIsDone(self, desired_state):
        """
        call this to check if the state of the hsb is already the desired one.
        :param desired_state: int, the desired state of the box
        :return: tuple, (bool_True_if_success, int_current_state, int_desired_state)
        """
        return True, desired_state, desired_state

    '''perform measurements:'''

    def measureOffset(self, scanpars, track_num, pre_post_scan_meas_str):
        """
        set all scanparameters at the fpga and go into the measure Offset state.
         set DAC to 0V
        :return:bool, True if successfully changed State
        """
        return True

    def measureTrack(self, scanpars, track_num):
        """
        set all scanparameters at the fpga and go into the measure Track state.
        Fpga will then measure one track independently from host and will finish either in
        'measComplete' or in 'error' state.
        In parallel, host has to read the data from the host sided buffer in parallel.
        :return:bool, True if successfully changed State
                always True in dummy Mode

        """
        self.status = TrsCfg.seqStateDict['measureTrack']
        logging.info('measuring track: ' + str(track_num) +
                     '\nscanparameters are:' + str(scanpars))
        self.data_builder(scanpars, track_num)
        return True

    def data_builder(self, scanpars, track_num):
        """
        build artificial data for one track.
        """
        track_ind, track_name = scanpars['pipeInternals']['activeTrackNumber']
        trackd = scanpars[track_name]
        logging.debug('starting to build artificial data for dummy trs for track %s' % track_name)
        logging.debug('num of steps: %s num of bins: %s num of bunches: %s num of scans: %s ' %
                      (trackd['nOfSteps'], trackd['nOfBins'], trackd['nOfBunches'], trackd['nOfScans']))
        count_in_every_bin = False  # set this to True to completly fill the time resolved matrix
        one_scan = self.build_one_scan(scanpars, trackd, track_ind, full=count_in_every_bin)
        one_scan_inverted = self.build_one_scan(scanpars, trackd, track_ind, True, full=count_in_every_bin)
        logging.debug('length of one_scan: %d, length of one_scan_inverted: %d'
                      % (len(one_scan), len(one_scan_inverted)))
        complete_lis = []
        for i in range(trackd['nOfScans']):
            complete_lis.append(Form.add_header_to23_bit(2, 4, 0, 1))  # means scan started
            complete_lis += one_scan if i % 2 == 0 or not trackd['invertScan'] else one_scan_inverted
            # if scan is inverted, use the data for an inverted scan on every odd scan number

        logging.debug('artificial data for dummy trs completed')
        self.artificial_build_data = complete_lis

    def build_one_scan(self, scanpars, trackd, track_ind, inverted=False, full=False):
        """ build data for one scan """
        num_bins = trackd['nOfBins']
        num_steps = trackd['nOfSteps']
        num_bunches = trackd['nOfBunches']

        if full:
            # a count in every bin
            # multiple counts when using more bunches per step
            count_time_dif = 1
            max_steps_one_pattern = 1
            reps_needed = num_steps
            cur_step = num_steps - 1 if inverted else 0
        else:
            # wanted pattern:
            # if the stepnumber is quite high, the pattern needs to be repeated,
            #  otherwise counts will overlap or exceed the time window
            # the minimal time difference is 1 = 10 ns
            # time
            # |         - max_t     -
            # |      -  -        -  -
            # |   -  -  -     -  -  -
            # |-  -  -  -  -  -  -  -  -
            # |__________________________ x axis
            #        max_step
            # the counts per "-" will be equal to the bunch number bunch0->1ct, ... bunch9->10cts

            count_time_dif = num_bins // (num_steps * num_bunches)  # problem if this is smaller than one!

            reps_needed = 1
            while count_time_dif < 2.0:
                # problem -> the pattern does not fit in one scan without touching
                # -> repeat the pattern!
                # increase reps_needed until count_time_dif is bigger than one
                reps_needed += 1
                count_time_dif = num_bins // ((num_steps * num_bunches) / reps_needed)

            max_steps_one_pattern = num_steps // reps_needed  # calculate the maximum step of one pattern
            cur_step = max_steps_one_pattern - 1 if inverted else 0
        logging.info('artificial build data in dummy trs'
                     ' with %d bunches, %d bins and %s steps must be repeated %d times'
                     ' time difference between counts is: %d'
                     ' The maximum step for one pattern is: %d'
                     % (num_bunches, num_bins, num_steps, reps_needed, count_time_dif, max_steps_one_pattern))

        # distribute pmts events all over time axis in last step
        # x_axis = Form.create_x_axis_from_scand_dict(scanpars)[track_ind]  # TODO this will cause problems if not dac
        # x_axis = [Form.add_header_to23_bit(x << 2, 3, 0, 1) for x in x_axis]  # here float shifting will fail
        one_scan = []  # flat list with all counts and events coming from the "fpga" datastream
        num_of_cts_per_bun_step = []
        one_rep_dac_missing = []  # list [ [one_step], [one_step], ... ]
        cur_step_evts = []
        scaler03 = 2 ** 4 - 1  # easier for debugging, all pmt have a count
        scaler47 = 2 ** 4 - 1  # easier for debugging, all pmt have a count
        if full:
            cur_bunch = 0
            while cur_bunch < num_bunches:
                if self.scan_dev == 'Triton':
                    # send next step request
                    cur_step_evts.append(Form.add_header_to23_bit(4, 4, 0, 1))  # means request next step
                cur_step_evts.append(Form.add_header_to23_bit(3, 4, 0, 1))  # means new bunch
                cur_bunc_cur_step_cts = []
                [[cur_bunc_cur_step_cts.append(Form.add_header_to23_bit(i, scaler03, scaler47, 0))
                  for i in range(num_bins)] for _ in range(cur_bunch + 1)]
                num_of_cts_per_bun_step.append((cur_step, cur_bunch, len(cur_bunc_cur_step_cts)))
                cur_step_evts += cur_bunc_cur_step_cts
                cur_bunch += 1
                if cur_bunch >= num_bunches:
                    # step complete, will be send after all bunches are completed
                    cur_step_evts.append(Form.add_header_to23_bit(1, int(b'0100', 2), 0, 1))
                one_rep_dac_missing.append(cur_step_evts)
        else:
            while cur_step < max_steps_one_pattern and not inverted or cur_step >= 0 and inverted:
                # count steps upwards if not inverted, otherwise count downwards
                cur_step_evts = []
                if cur_step % 2 == 1:
                    cur_bunch = 0  # set bunch to 0 in order to create cts below
                else:  # no scaler entries for all even step numbers
                    cur_bunch = num_bunches
                    for bun in range(cur_bunch):  # add as meany bunch complete infos as needed to complete this step
                        if self.scan_dev == 'Triton':
                            # send next step request
                            cur_step_evts.append(Form.add_header_to23_bit(4, 4, 0, 1))  # means request next step
                        cur_step_evts.append(Form.add_header_to23_bit(3, 4, 0, 1))  # means new bunch
                    cur_step_evts.append(Form.add_header_to23_bit(1, int(b'0100', 2), 0, 1))  # step complete
                while cur_bunch < num_bunches:  # only for uneven steps
                    if self.scan_dev == 'Triton':
                        # send next step request
                        cur_step_evts.append(Form.add_header_to23_bit(4, 4, 0, 1))  # means request next step
                    cur_step_evts.append(Form.add_header_to23_bit(3, 4, 0, 1))  # means new bunch
                    time_offset_cur_bunch_cur_step = cur_bunch * cur_step
                    cur_bunc_cur_step_cts = []
                    [[cur_bunc_cur_step_cts.append(Form.add_header_to23_bit(
                        int(count_time_dif * (i + time_offset_cur_bunch_cur_step)),
                        scaler03, scaler47, 0))
                        for i in range(cur_step)] for _ in range(cur_bunch + 1)]
                    num_of_cts_per_bun_step.append((cur_step, cur_bunch, len(cur_bunc_cur_step_cts)))
                    cur_step_evts += cur_bunc_cur_step_cts
                    # add pmt events with time difference count_time_dif * stepIndex
                    cur_bunch += 1
                    if cur_bunch >= num_bunches:
                        # step complete, will be send after all bunches are completed
                        cur_step_evts.append(Form.add_header_to23_bit(1, int(b'0100', 2), 0, 1))
                cur_step += -1 if inverted else 1
                one_rep_dac_missing.append(cur_step_evts)

        for cur_step_one_scan in range(num_steps):
            # one_scan += int(x_axis[cur_step_one_scan]),  # start with dac information
            one_scan += one_rep_dac_missing[cur_step_one_scan % max_steps_one_pattern]

        logging.debug('one scan was created. [(step, bunch, #cts)] were set: %s' % str(num_of_cts_per_bun_step))
        return one_scan

    ''' overwriting interface functions here '''

    def getData(self):
        """
        nOfEle = int, number of Read Elements,
        newDataArray = numpy Array containing all data that was read
        elemRemainInFifo = int, number of Elements still in FifoBuffer
        :return:
        """
        st = datetime.now()
        result = {'nOfEle': 0, 'newData': None, 'elemRemainInFifo': 0}
        produce_error = False  # set to True if you want the scan to fail
        if produce_error:
            self.status = TrsCfg.seqStateDict['error']
        else:
            result['elemRemainInFifo'] = len(self.artificial_build_data)
            if self.pause_bool:  # scan is paused, return no data
                return result
            else:
                max_read_data = 2000
                n_of_read_data = 0
                if result['elemRemainInFifo'] > 0:
                    n_of_read_data = min(max_read_data, result['elemRemainInFifo'])
                    result['newData'] = np.array(self.artificial_build_data[0:n_of_read_data])
                    result['nOfEle'] = n_of_read_data
                    result['elemRemainInFifo'] = len(self.artificial_build_data) - n_of_read_data
                self.artificial_build_data = self.artificial_build_data[n_of_read_data:]
                if result['elemRemainInFifo'] == 0:
                    self.status = TrsCfg.seqStateDict['measComplete']
                elapsed = datetime.now() - st
                # logging.debug('reading from dummy trs sequencer took %.1f ms ' % (elapsed.total_seconds() * 1000))
        return result

    def getSeqState(self):
        return self.status

    def abort(self):
        self.artificial_build_data = []
        return True

    def halt(self, val):
        logging.info('Halt in dummy mode will not finish this scan but abort!')
        self.artificial_build_data = []
        return True

    def pause_scan(self, pause_bool=None):
        if pause_bool is None:
            pause_bool = not self.pause_bool
        logging.info('pausing the dummy, pause is: %s' % pause_bool)
        self.pause_bool = pause_bool
        return True

    def DeInitFpga(self, finalize_com=False):
        return True

    def FinalizeFPGACom(self):
        return True

    def set_stopVoltMeas(self, stop_bool):
        return True

    def read_outbits_state(self):
        return 0, 'dummy'

    def read_outbits_number_of_cmds(self):
        return 0, 0, 0

# scanp = DftSc.draftScanDict
# test = TimeResolvedSequencer()
# test.data_builder(scanp, 0)
# print(len(test.artificial_build_data))
# print(list(map(Form.split_32b_data, test.artificial_build_data)))
