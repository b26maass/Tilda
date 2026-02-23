"""
Created on 

@author: simkaufm

Module Description: Module to hanlde the information coming from the fpga,

32-bit input must begin with 'firstHeader' = 0100 and 'headerIndex' = 1
"""
import logging


class InfoHandler:
    def __init__(self):
        self.started_bunches_in_step = 0
        self.volt_index = 0
        self.total_started_bunches = 0
        self.total_completed_steps = 0
        self.total_started_scans = 0

    def setup(self):
        self.started_bunches_in_step = 0
        self.volt_index = 0
        self.total_started_bunches = 0
        self.total_completed_steps = 0
        self.total_started_scans = 0

    def clear(self):
        self.setup()

    def info_handle(self, pipe_data, payload):
        """
        call this whenever an info 32b element is read from fpga.
        This function will return the current voltage index.
        """
        step_complete = False
        track_ind, track_name = pipe_data['pipeInternals']['activeTrackNumber']
        if payload == 1:  # means step complete
            step_complete = True
            self.started_bunches_in_step = 0
            self.total_completed_steps += 1
            pipe_data[track_name]['nOfCompletedSteps'] += 1

            self.volt_index += self.sign_for_volt_ind(pipe_data[track_name]['invertScan'])
            # logging.debug('infohandler: total num of steps completed: ' + str(self.total_completed_steps))
            # logging.debug('infohandler: step completed, voltindex is: ' + str(self.volt_index))
            return self.volt_index, step_complete

        elif payload == 2:  # means scan started
            self.total_started_scans += 1
            if pipe_data[track_name]['invertScan']:  # if inverted, take last element on every second scan
                if self.total_started_scans % 2 == 0:
                    self.volt_index = -1
                    return self.volt_index, step_complete
                else:
                    self.volt_index = 0
            else:
                self.volt_index = 0
            # logging.debug('infohandler: next scan started ' + str(self.total_started_scans) + ' voltindex: ' + str(self.volt_index))
            return self.volt_index, step_complete

        elif payload == 3:  # means new bunch
            self.started_bunches_in_step += 1
            self.total_started_bunches += 1
            # logging.debug('infohandler: total num of bunches started: ' + str(self.total_started_bunches))
            # logging.debug('infohandler: num of bunches started in this step: ' + str(self.started_bunches_in_step))
            return None, step_complete

        elif payload == 4:  # means preparing next step
            # This will not be handled by InfoHandler but in a separate node.
            return None, step_complete

        logging.warning('InfoHandler received unknown payload: %s', payload)
        return None, step_complete

    def sign_for_volt_ind(self, invert_scan):
        even_scan_num = self.total_started_scans % 2 == 0
        if invert_scan:
            if even_scan_num:  # in every even scan, scan dir turns around
                return -1
            else:
                return 1
        return 1
