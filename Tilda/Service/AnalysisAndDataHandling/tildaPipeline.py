"""

Created on '20.05.2015'

@author:'simkaufm'

"""

import logging
import os

import matplotlib.pyplot as plt

import Tilda.Service.AnalysisAndDataHandling.tildaNodes as TN
from Tilda.PolliFit.polliPipe.simpleNodes import NPrint
from Tilda.PolliFit.polliPipe.node import Node
from Tilda.PolliFit.polliPipe.pipeline import Pipeline


def find_pipe_by_seq_type(scan_dict, callback_sig, live_plot_callback_tuples,
                          fit_res_callback_dict, scan_complete_callback, dac_new_volt_set_callback,
                          scan_start_stop_tr_wise=None, bunch_start_stop_tr_wise=None, next_step_request_sig=None):
    seq_type = scan_dict['isotopeData']['type']
    if seq_type == 'cs' or seq_type == 'csdummy':
        logging.debug('loading pipeline of type: cs')
        return CsPipe(scan_dict, callback_sig, live_plot_callbacks=live_plot_callback_tuples,
                      next_step_request_sig=next_step_request_sig)
    elif seq_type == 'trs' or seq_type == 'trsdummy':
        logging.debug('loading pipeline of type: trs')
        return TrsPipe(scan_dict, callback_sig,
                       live_plot_callbacks=live_plot_callback_tuples,
                       scan_start_stop_tr_wise=scan_start_stop_tr_wise,
                       bunch_start_stop_tr_wise=bunch_start_stop_tr_wise,
                       next_step_request_sig=next_step_request_sig)
    elif seq_type == 'kepco':
        logging.debug('loading pipeline of type: kepco')
        return kepco_scan_pipe(scan_dict, callback_sig,
                               as_voltage=True,
                               live_plot_callbacks=live_plot_callback_tuples,
                               fit_res_dict_callback=fit_res_callback_dict,
                               scan_complete_callback=scan_complete_callback,
                               dac_new_volt_set_callback=dac_new_volt_set_callback,
                               next_step_request_sig=next_step_request_sig)
    else:
        return None


def TrsPipe(initialScanPars=None, callback_sig=None, x_as_voltage=True,
            live_plot_callbacks=None, scan_start_stop_tr_wise=None, bunch_start_stop_tr_wise=None,
            next_step_request_sig=None):
    """
    Pipeline for the dataflow and analysis of one Isotope using the time resolved sequencer.
    Mutliple Tracks are supported.
    always feed raw data.
    """
    if live_plot_callbacks is None:
        live_plot_callbacks = (None, None, None, None, None, None)
    start = Node()

    pipe = Pipeline(start)

    pipe.pipeData = initPipeData(initialScanPars)
    # walk = start.attach(SN.NPrint())

    # alternative pipeline:
    fast = start.attach(TN.NFilterDMMDictsAndSave(live_plot_callbacks[4]))  # Replaced former NFilterDMMDicts AndSave
    # fast = fast.attach(TN.NROCTrigger())

    # # use the sleep node in order to simulate long processing times in pipeline
    # fast = fast.attach(TN.NSleep(sleeping_time_s=2.0))
    fast = fast.attach(TN.NSaveRawData())
    fast = fast.attach(TN.NSendNextStepRequestViaQtSignal(next_step_request_sig))
    # fast = fast.attach(TN.NProcessQtGuiEvents())
    fast = fast.attach(TN.NTRSSortRawDatatoArrayFast(scan_start_stop_tr_wise=scan_start_stop_tr_wise,
                                                     bunch_start_stop_tr_wise=bunch_start_stop_tr_wise))
    # fast = fast.attach(TN.NProcessQtGuiEvents())
    fast = fast.attach(TN.NSendnOfCompletedStepsViaQtSignal(callback_sig))
    # fast = fast.attach(SN.NPrint())
    # old = fast.attach(TN.NTRSSumFastArrays())  # outdated
    fast_spec = fast.attach(TN.NTRSSumFastArraysSpecData(x_as_voltage=x_as_voltage))
    # fast = fast.attach(TN.NProcessQtGuiEvents())

    # fast = fast.attach(SN.NPrint())

    # old_spec = old.attach(TN.NSortedZeroFreeTRSDat2SpecData())  # outdated
    # fast_spec = fast_spec.attach(TN.NProcessQtGuiEvents())
    # old_spec = old_spec.attach(TN.NSpecDataZeroFreeProjection())  # outdated
    # fast_spec = fast_spec.attach(TN.NProcessQtGuiEvents())
    # fast_spec = fast_spec.attach(SN.NPrint())
    fast_spec = fast_spec.attach(TN.NMPLImagePlotAndSaveSpecData(0, *live_plot_callbacks))
    # fast_spec = fast_spec.attach(TN.NProcessQtGuiEvents())

    # fast_spec = fast_spec.attach(TN.NSaveSpecData())
    compl_tr_br = fast.attach(TN.NCheckIfTrackComplete())
    compl_tr_br = compl_tr_br.attach(TN.NAddWorkingTimeOnStart(True))
    # compl_tr_br = compl_tr_br.attach(SN.NPrint())
    return pipe


def CsPipe(initialScanPars=None, callback_sig=None, live_plot_callbacks=None, next_step_request_sig=None):
    """
    Pipeline for the dataflow and analysis of one Isotope using the continous sequencer.
    always feed raw data.
    """
    start = Node()
    if live_plot_callbacks is None:
        live_plot_callbacks = (None, None, None, None, None, None)

    pipe = Pipeline(start)
    # start = start.attach(SN.NPrint())
    start = start.attach(TN.NFilterDMMDictsAndSave(live_plot_callbacks[4]))  # Replaced former NFilterDMMDicts

    maintenance = start.attach(TN.NMPLCloseFigOnInit())

    fig, axes = plt.subplots(5, sharex=True)
    pipe.pipeData = initPipeData(initialScanPars)

    filen = os.path.split(pipe.pipeData['pipeInternals']['activeXmlFilePath'])[1]
    window_title = 'plot ' + filen
    fig.canvas.manager.set_window_title(window_title)

    walk = start.attach(TN.NSaveRawData())
    # walk = start.attach(TN.NSplit32bData())
    #
    walk = walk.attach(TN.NSendNextStepRequestViaQtSignal(next_step_request_sig))
    walk = walk.attach(TN.NCSSortRawDatatoArray())
    walk = walk.attach(TN.NSendnOfCompletedStepsViaQtSignal(callback_sig))

    walk = walk.attach(TN.NRemoveTrackCompleteFlag())
    walk = walk.attach(TN.NCSSum())

    spec = walk.attach(TN.NCS2SpecData())
    spec = spec.attach(TN.NMPLImagePlotAndSaveSpecData(0, *live_plot_callbacks))

    compl_tr_br = spec.attach(TN.NCheckIfTrackComplete())
    compl_tr_br = compl_tr_br.attach(TN.NAddWorkingTimeOnStart(True))

    return pipe


def kepco_scan_pipe(initial_scan_pars, callback_sig=None, as_voltage=False,
                    live_plot_callbacks=None, fit_res_dict_callback=None, scan_complete_callback=None,
                    dac_new_volt_set_callback=None, next_step_request_sig=None):
    """
    pipeline for the measurement and analysis of a kepco scan
    raw data and readback from dmm are fed into the pipeline.
    :param initial_scan_pars: full scan dictionary which will be used as starting point for this pipeline
    always feed raw data.
    """
    start = Node()

    maintenance = start.attach(TN.NAddWorkingTimeOnStart(True))
    if live_plot_callbacks is None:
        live_plot_callbacks = (None, None, None, None, None, None)

    pipe = Pipeline(start)
    pipe.pipeData = initPipeData(initial_scan_pars)

    # kepco scan should always just have one track
    dmm_names = sorted(list(pipe.pipeData['track0']['measureVoltPars']['duringScan']['dmms'].keys()))
    #
    # raw data for kepco -> dict -> cannot be saved with hdf5 -> do not save raw data
    # walk = start.attach(TN.NSaveRawData())
    # debug = start.attach(SN.NPrint())
    specdata_path = start.attach(TN.NSendNextStepRequestViaQtSignal(next_step_request_sig))
    specdata_path = specdata_path.attach(TN.NStartNodeKepcoScan(as_voltage, dmm_names,
                                                                scan_complete_callback, dac_new_volt_set_callback))
    specdata_path = specdata_path.attach(TN.NSendnOfCompletedStepsViaQtSignal(callback_sig))

    specdata_path = specdata_path.attach(TN.NMPLImagePlotAndSaveSpecData(0, *live_plot_callbacks))

    specdata_path = specdata_path.attach(TN.NStraightKepcoFitOnClear(dmm_names,
                                                                     gui_fit_res_callback=fit_res_dict_callback))
    return pipe


def initPipeData(initialScanPars):
    """
    initialize the pipeData used for the analysis Pipeline
    -> store the initialScanPars in the pipe.pipeData and create an .xml file
    :return: dict, {'isotopeData', 'progConfigs', 'track0', 'pipeInternals'}
    always feed raw data.
    """
    pipeData = initialScanPars

    # trackDict = pipeData['track0']
    # trackDict.update(dacStartVoltage=get_voltage_from_18bit(trackDict['dacStartRegister18Bit']))
    # trackDict.update(dacStopVoltage=get_voltage_from_18bit(
    #     VCon.calc_scan_dev_stop_val(trackDict['dacStartRegister18Bit'],
    #                              trackDict['dacStepSize18Bit'],
    #                              trackDict['nOfSteps'])))

    # pipeData['pipeInternals']['curVoltInd'] = 0
    # pipeData['isotopeData']['isotopeStartTime'] = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
    # xml_file_name = TildaTools.createXmlFileOneIsotope(pipeData)
    # pipeData['pipeInternals']['activeXmlFilePath'] = xml_file_name

    # in the past an extra projection file was created. but for now,
    #  the projection should stay within the .xml file for this scan.
    # if pipeData['isotopeData']['type'] in ['trs', 'trsdummy']:
    #     pipeData['pipeInternals']['activeXmlProjFilePath'] = FaFH.createXmlFileOneIsotope(
    #         pipeData, 'trs_proj', xml_file_name.replace('.xml', '_proj.xml'))
    return pipeData


def simple_counter_pipe(qt_sig, act_pmt_list, sample_interval):
    """
    pipeline for analysis and displaying while the simple counter is running.
    always feed raw data.
    """
    start = Node()

    # fig, axes = plt.subplots(len(act_pmt_list), sharex=True)
    # fig.canvas.set_window_title('Simple Counter')

    datapoints = 1 / sample_interval  # values per second, fpga samples at 200ms currently
    pipe = Pipeline(start)

    start = start.attach(TN.NFilterDMMDicts())

    walk = start.attach(TN.NSplit32bData())
    # walk = walk.attach(SN.NPrint())

    walk = walk.attach(TN.NSPSortByPmt(datapoints))
    # walk = walk.attach(TN.NSumListsInData())
    # walk = walk.attach(SN.NPrint())
    walk = walk.attach(TN.NSendDataViaQtSignal(qt_sig))
    # walk = walk.attach(TN.NMPLCloseFigOnClear(fig))
    # walk = walk.attach(SN.NPrint())
    #
    # walk = walk.attach(TN.NSPAddxAxis())
    # pmt_dict = {}
    # for pmt_ind, pmt_num in enumerate(act_pmt_list):
    #     pmt_dict['pmt' + str(pmt_num)] = walk.attach(TN.NOnlyOnePmt(pmt_num))
    #     pmt_dict['pmt' + str(pmt_num)] = pmt_dict['pmt' + str(pmt_num)].attach(
    #         TN.NMPlLivePlot(axes[pmt_ind], 'mov. avg. Ch %s' % pmt_num, ['blue']))
    #
    # draw = pmt_dict['pmt' + str(act_pmt_list[-1])].attach(TN.NMPlDrawPlot())

    return pipe


def tilda_passive_pipe(initial_scan_pars, raw_callback, steps_scans_callback):
    """
    pipeline for running the tilda passive mode.
    always feed raw data.
    """
    start = Node()

    pipe = Pipeline(start)
    initial_scan_pars['track0']['nOfSteps'] = None
    initial_scan_pars['track0']['nOfScans'] = 0
    pipe.pipeData = initPipeData(initial_scan_pars)

    start = start.attach(TN.NFilterDMMDicts())

    maintenance = start.attach(TN.NMPLCloseFigOnInit())
    maintenance = maintenance.attach(TN.NAddWorkingTimeOnClear(True))

    # walk = start.attach(SN.NPrint())
    walk = start.attach(TN.NSendDataViaQtSignal(raw_callback))
    walk = walk.attach(TN.NSaveRawData())
    walk = walk.attach(TN.NTiPaAccRawUntil2ndScan(steps_scans_callback))
    # walk = walk.attach(SN.NPrint())

    # walk = walk.attach(TN.NSplit32bData())
    walk = walk.attach(TN.NCSSortRawDatatoArray())
    walk = walk.attach(TN.NSendnOfCompletedStepsAndScansViaQtSignal(steps_scans_callback))
    walk = walk.attach(TN.NRemoveTrackCompleteFlag())
    walk = walk.attach(TN.NCSSum())
    # walk = walk.attach(SN.NPrint())

    pl_branch_2d = walk.attach(TN.NMPLImagePLot(1, False))
    pl_branch_2d = pl_branch_2d.attach(TN.NMPlDrawPlot())
    #
    # compl_tr_br = walk.attach(TN.NCheckIfTrackComplete())
    #
    # # meas_compl_br = walk.attach(TN.NCheckIfMeasurementComplete())
    walk = walk.attach(TN.NSaveAllTracks())
    # #
    walk = walk.attach(TN.NTRSProjectize(False))
    walk = walk.attach(TN.NSaveProjection())

    return pipe


def time_resolved_display(filepath, liveplot_callbacks):
    """
    pipeline for displaying a time resolved spectra.
    feed only time resolved specdata to it!
    """
    start = Node()

    pipe = Pipeline(start)
    if liveplot_callbacks is None:
        liveplot_callbacks = (None, None, None, None, None, None)

    pipe.pipeData['pipeInternals'] = {}

    pipe.pipeData['pipeInternals']['activeXmlFilePath'] = filepath
    # scan_dict, xml_etree = TildaTools.scan_dict_from_xml_file(filepath, pipe.pipeData)
    # pipe.pipeData = scan_dict
    pipe.pipeData['pipeInternals']['activeTrackNumber'] = (0, 'track0')

    # path of file is used mainly for the window title.
    walk = start.attach(NPrint())
    # walk = walk.attach(TN.NMPLImagePlotSpecData(0, dataPath))
    walk = walk.attach(TN.NMPLImagePlotAndSaveSpecData(0, *liveplot_callbacks))
    # walk = walk.attach(TN.NMPlDrawPlot())

    return pipe
