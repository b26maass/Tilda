"""

Created on '20.08.2015'

@author:'simkaufm'

"""

import functools
import logging
import sys

from copy import deepcopy

import numpy as np

logging.basicConfig(level=getattr(logging, 'INFO'), format='%(message)s', stream=sys.stdout)
import pyqtgraph as pg

pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

# brush_k = pg.mkBrush(0, 0, 0, 255)
# brush_b = pg.mkBrush(0, 0, 255, 255)

track_colors = ['k', 'r', 'y', 'g', 'c', 'b', 'm']


def get_track_color(track_index):
    return track_colors[track_index % len(track_colors)]


def plot_x_y(x, y):
    """
    Create and return a :class:`PlotWindow <pyqtgraph.PlotWindow>`
    (this is just a window with :class:`PlotWidget <pyqtgraph.PlotWidget>` inside), plot data in it.
    Accepts a *title* argument to set the title of the window.
    All other arguments are used to plot data. (see :func:`PlotItem.plot() <pyqtgraph.PlotItem.plot>`)
    """
    win = pg.plot(x=x, y=y)

    return win


def plot_spec_data(spec_data, sc, tr, plot_item=None, pen='k'):
    x, y, err = spec_data.getArithSpec(sc, tr)
    if plot_item is None:
        return plot_x_y(x, y)
    else:
        plot_item.plot(x, y, pen=pen)


def plot_std(x, y, err, std_plt, err_plt, stepMode=True, break_points=None, color='k'):
    """
    Create and plot new plotData in a standard pyqtgraph x-y-plot.

    :param x: The x values.
    :param y: The y values.
    :param err: The y uncertainties.
    :param std_plt: The plot item for the values.
    :param err_plt: The plot item for the uncertainties.
    :param stepMode: Whether to plot bins (without uncertainties) or points with error bars.
    :param break_points: The points at which to separate the histogram if stepMode.
    :param color: The color of the data.
    :return: None.
    """
    if isinstance(stepMode, bool):
        stepMode = 'center' if stepMode else None
    if stepMode is not None:
        std_data = std_plt.plot(convert_xaxis_for_step_mode(x, break_points=break_points),
                                convert_yaxis_for_step_mode(y, break_points=break_points),
                                stepMode=stepMode, symbol=None, pen=color)
        err_plt.setData(x=[], y=[], height=None)
    else:
        std_data = std_plt.plot(x, y, stepMode=None, symbol='o', pen=None, symbolBrush=pg.mkBrush(color), symbolSize=5)
        err_plt.setData(x=x, y=y, height=2 * err, beam=(x[1] - x[0]) / 2, pen=color)
    return std_data


def set_data_std(x, y, err, std_plt, err_plt, stepMode=True, break_points=None, color='k'):
    """
    Set new data in a standard pyqtgraph x-y-plot.

    :param x: The x values.
    :param y: The y values.
    :param err: The y uncertainties.
    :param std_plt: The plot item for the values.
    :param err_plt: The plot item for the uncertainties.
    :param stepMode: Whether to plot bins (without uncertainties) or points with error bars.
    :param break_points: The points at which to separate the histogram if stepMode.
    :param color: The color of the data.
    :return: None.
    """
    if isinstance(stepMode, bool):
        stepMode = 'center' if stepMode else None
    if stepMode is not None:
        std_plt.setData(convert_xaxis_for_step_mode(x, break_points=break_points),
                        convert_yaxis_for_step_mode(y, break_points=break_points),
                        stepMode=stepMode, symbol=None, pen=color)
        err_plt.setData(x=[], y=[], height=None)
    else:
        std_plt.setData(x, y, stepMode=None, symbol='o', pen=None, symbolBrush=pg.mkBrush(color), symbolSize=5)
        err_plt.setData(x=x, y=y, height=2 * err, beam=(x[1] - x[0]) / 2, pen=color)


def create_image_view(x_label='line voltage', y_label='time / µs'):
    plt_item = pg.PlotItem()
    imv_widget = pg.ImageView(view=plt_item)
    plt_item.invertY(False)
    plt_item.showAxis('top')
    plt_item.showAxis('right')
    plt_item.showLabel('bottom', False)
    plt_item.showLabel('right', False)
    plt_item.getAxis('right').setStyle(showValues=False)
    plt_item.getAxis('bottom').setStyle(showValues=False)
    plt_item.setLabel('left', y_label)
    plt_item.setLabel('top', x_label)
    colors = [
        (255, 255, 255),
        (0, 0, 255),
        (0, 255, 255),
        (0, 255, 0),
        (255, 255, 0),
        (255, 0, 0),
    ]
    color = pg.ColorMap(pos=np.linspace(0.0, 1.0, len(colors)), color=colors)
    imv_widget.setColorMap(color)
    return imv_widget, plt_item


def create_x_y_widget(do_not_show_label=None, x_label='line voltage', y_label='cts'):
    if do_not_show_label is None:
        do_not_show_label = ['top', 'right']
    widg = pg.PlotWidget()
    plt_item = widg.getPlotItem()
    plt_item.showAxis('top')
    plt_item.showAxis('right')
    for ax in do_not_show_label:
        plt_item.showLabel(ax, False)
        plt_item.getAxis(ax).setStyle(showValues=False)
    if 'left' not in do_not_show_label or 'right' not in do_not_show_label:
        plt_item.setLabel('left' if 'left' not in do_not_show_label else 'right', y_label)
    if 'bottom' not in do_not_show_label or 'top' not in do_not_show_label:
        plt_item.setLabel('bottom' if 'bottom' not in do_not_show_label else 'top', x_label)
    return widg, plt_item


def create_plot_for_all_sc(
        target_layout, pmt_list, slot_for_mouse_move, max_rate, plot_sum=True, inf_line=True, y_label='cts'):
    """

    this will add a pyqtgraph widget for each scaler and an additional one for the sum to the target layout.
    :param target_layout: QtLayout, here the widgets will be added
    :param pmt_list: list, containing the indices/numbers of the scalers, use specdata.active_pmt_list[tr]
    :param slot_for_mouse_move:
    :param max_rate:
    :param plot_sum:
    :param inf_line:
    :param y_label:
    :return: list, of dicts, {'widget', 'proxy', 'vertLine', 'indList', 'pltDataItem', 'name', 'pltItem', 'fitLine'}
     with sum at the last position.
    """
    return_list = []
    max_rate = max_rate
    for sc_ind, sc_name in enumerate(pmt_list):
        label_list = ['top', 'right', 'bottom']
        if not plot_sum:  # if the sum is not plotted, the last pmt must hold the label
            label_list = label_list if sc_ind < len(pmt_list) - 1 else ['top', 'right']
        widg, plt_item = create_x_y_widget(do_not_show_label=label_list, y_label='sc{} ({})'.format(sc_name, y_label))
        plt_proxy = create_proxy(signal=plt_item.scene().sigMouseMoved,
                                 slot=functools.partial(slot_for_mouse_move, plt_item.vb, False),
                                 rate_limit=max_rate)
        err_plt_item = create_error_item()
        if sc_ind:  # link to the plot before in list, not in first index(=0) of course
            plt_item.vb.setXLink(return_list[-1]['pltItem'].getViewBox())
        plt_data_item = plt_item.plot(pen='k')
        if inf_line:
            plt_inf_line = create_infinite_line(0, pen='r')
            plt_item.addItem(plt_inf_line)
        else:
            plt_inf_line = None
        singl_dict = {
            'name': str(sc_name),
            'indList': [sc_ind],
            'widget': widg,
            'proxy': plt_proxy,
            'vertLine': plt_inf_line,
            'pltItem': plt_item,
            'pltErrItem': err_plt_item,
            'pltDataItem': plt_data_item,
            'fitLine': None
        }
        return_list.append(singl_dict)
        target_layout.addWidget(widg)
    if plot_sum:
        sum_wid, sum_plt_item = create_x_y_widget(
            do_not_show_label=['top', 'right'], y_label='sum ({})'.format(y_label))
        sum_proxy = create_proxy(signal=sum_plt_item.scene().sigMouseMoved,
                                 slot=functools.partial(slot_for_mouse_move, sum_plt_item.vb, False),
                                 rate_limit=max_rate)
        err_sum_plt_item = create_error_item()
        sum_plt_data_item = sum_plt_item.plot(pen='b')
        if inf_line:
            sum_inf_line = create_infinite_line(0, pen='r')
            sum_plt_item.addItem(sum_inf_line)
        else:
            sum_inf_line = None
        target_layout.addWidget(sum_wid)
        sum_plt_item.vb.setXLink(return_list[-1]['pltItem'].getViewBox())
        sum_dict = {
            'name': 'sum',
            'indList': range(0, len(pmt_list)),
            'widget': sum_wid,
            'proxy': sum_proxy,
            'vertLine': sum_inf_line,
            'pltItem': sum_plt_item,
            'pltErrItem': err_sum_plt_item,
            'pltDataItem': sum_plt_data_item,
            'fitLine': None
        }
        return_list.append(sum_dict)
    return return_list


def plot_all_sc_new(list_of_widgets_etc, spec_data, tr, func, stepMode=True, break_points=None):
    """
    create plots in the all pmts tab
    :param list_of_widgets_etc: list of widgest, containig widgets to be plotted
    :param spec_data: SpecDat, used spectrum
    :param tr: list of int, used tracks, -1 for all
    :param func: str, users function
    :param stepMode: Whether to plot bins (without uncertainties) or points with error bars.
    :param break_points: The points at which to separate the histogram if stepMode.
    """
    for val in list_of_widgets_etc:
        sc = val['indList']  # which scalers are needed for this plot?
        plt_data_itm = val['pltDataItem']  # data needed for this plot
        plt_err_itm = val['pltErrItem']  # error item needed for this plot
        eval_on = False
        color = 'k'
        if val['name'] == 'sum':
            eval_on = True  # only for this plot an evaluation is needed
            color = 'b'

        # x, y, err = spec_data.calcSpec(func, tr, sc, eval_on)   # calc arithmetic plot
        x, y, err = spec_data.getArithSpec(sc, tr, func, eval_on=eval_on)

        set_data_std(x, y, err, plt_data_itm, plt_err_itm, stepMode=stepMode, break_points=break_points, color=color)

        # if stepMode:
        #     x = convert_xaxis_for_step_mode(deepcopy(x))
        # plt_data_itm.setData(x, y, stepMode=stepMode)


def plot_all_sc(list_of_widgets_etc, spec_data, tr, stepMode=True, break_points=None):
    # print('plotting all pmts in %s' % list_of_widgets_etc)
    for val in list_of_widgets_etc:
        sc = val['indList']
        plt_data_itm = val['pltDataItem']
        x, y, err = spec_data.getArithSpec(sc, tr)
        # x, y, err = spec_data.getArithSpec(sc, tr)
        if isinstance(stepMode, bool):
            if stepMode:
                x = convert_xaxis_for_step_mode(x, break_points=break_points)
                y = convert_yaxis_for_step_mode(y, break_points=break_points)
                stepMode = 'center'
            else:
                stepMode = None
        plt_data_itm.setData(x, y, stepMode=stepMode)


def convert_xaxis_for_step_mode(x_axis, break_points=None):
    # Do not use the legacy function for more than a single track.
    if break_points is None:
        x_axis_step = np.mean(np.ediff1d(x_axis))
        x_axis = np.append(x_axis, [x_axis[-1] + x_axis_step])
        x_axis += -0.5 * abs(x_axis_step)
        return x_axis
    i = 0
    x_axes = []
    for j in break_points:
        _x_axis = x_axis[slice(i, j, 1)]
        _x_axis_step = np.mean(np.ediff1d(_x_axis))
        _x_axis = np.append(_x_axis, [_x_axis[-1] + _x_axis_step])
        _x_axis += -0.5 * abs(_x_axis_step)
        x_axes.append(_x_axis)
        i = j
    return np.concatenate(x_axes, axis=0)


def convert_yaxis_for_step_mode(y_axis, break_points=None):
    # Do not use the legacy function for more than a single track.
    if break_points is None or len(break_points) < 2:
        return y_axis
    return np.insert(y_axis, break_points[:-1], np.min(y_axis))


def create_viewbox():
    return pg.ViewBox()


def create_plotitem():
    return pg.PlotItem()


def create_plot_data_item(x, y, pen='b', stepMode=False):
    if isinstance(stepMode, bool):
        stepMode = 'center' if stepMode else None
    return pg.PlotDataItem(x, y, pen=pen, stepMode=stepMode)


def create_axisitem(orientation):
    return pg.AxisItem(orientation)


def create_error_item():
    return pg.ErrorBarItem(x=[], y=[])


def create_fill_between_item(curve1, curve2, brush='b', pen=None):
    return pg.FillBetweenItem(curve1, curve2, brush=brush, pen=pen)


def image(data):
    return pg.image(data)


def create_proxy(signal, slot, rate_limit=60):
    proxy = pg.SignalProxy(signal, rateLimit=rate_limit, slot=slot)
    return proxy


def create_roi(pos, size):
    roi = pg.ROI(pos, size, pen=pg.mkPen('k', width=1.5))
    # Use cosmetic pens for handles so they keep a fixed on-screen size while zooming.
    # A raw QPen scales with the view transform and can appear as large pink blocks.
    roi.handlePen = pg.mkPen(255, 0, 200, width=1)
    roi.handleHoverPen = pg.mkPen(255, 0, 200, width=2)

    def hoverColor():
        # Generate the pen color for this ROI when the mouse is hovering over it
        if roi.mouseHovering:
            return pg.mkPen(255, 0, 200, width=2)
        else:
            return roi.pen
    roi._makePen = hoverColor
    # handles scaling horizontally around center
    roi.addScaleHandle([1, 0.5], [0.5, 0.5])
    roi.addScaleHandle([0, 0.5], [0.5, 0.5])

    # handles scaling vertically from opposite edge
    roi.addScaleHandle([0.5, 0], [0.5, 1])
    roi.addScaleHandle([0.5, 1], [0.5, 0])

    # handles scaling both vertically and horizontally
    roi.addScaleHandle([1, 1], [0, 0])
    roi.addScaleHandle([0, 0], [1, 1])
    return roi


def create_infinite_line(pos, angle=90, pen=0.5, movable=False):
    inf_line = pg.InfiniteLine(pos, angle=angle, pen=pen, movable=movable)
    return inf_line


def create_text_item(text="", color=(200, 200, 200), html=None, anchor=(0, 0)):
    return pg.TextItem(text=text, color=color, html=html, anchor=anchor)


def start_examples():
    import pyqtgraph.examples
    pyqtgraph.examples.run()


def create_roi_polyline(positions, closed=False, pos=None, **args):
    return MyPolyLineRoi(positions, closed, pos, **args)


def create_pen(*args, **kargs):
    return pg.mkPen(*args, **kargs)


def create_brush(*args, **kargs):
    return pg.mkBrush(*args, **kargs)


class MyPolyLineRoi(pg.PolyLineROI):
    """ subclassing the PolyLineROI and overwrites the checkPointMove to always return False """
    def __init__(self, positions, closed, pos, **args):
        super(MyPolyLineRoi, self).__init__(positions, closed, pos, **args)

    def checkPointMove(self, handles, pos, modifiers):
        """When handles move, they must ask the ROI if the move is acceptable.
         By default, this always returns True. Subclasses may wish override.
         -> always returning False therefore user cannot change this.
          Maybe change this to a clever way in the future """
        return False

    def segmentClicked(self, segment, ev=None, pos=None):  # pos should be in this item's coordinate system
        """ do not add a handle on clicking on the line """
        pass

    def checkRemoveHandle(self, h):
        """ do not allow to remove a handle """
        return False

# import sys
# from PyQt5 import QtWidgets
# import pyqtgraph as pg
#
#
# if __name__=='__main__':
#     app = QtWidgets.QApplication(sys.argv)
#     pg.plot(x=[0, 1, 2], y=[1, 3, 0])
#     status = app.exec_()
#     sys.exit(status)


if __name__ == '__main__':
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication(sys.argv)
    start_examples()
    status = app.exec_()
    sys.exit(status)
