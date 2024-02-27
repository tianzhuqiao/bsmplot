import sys
import re
import json
import traceback
import datetime
import multiprocessing as mp
from collections.abc import MutableMapping
import collections
import six.moves.queue as Queue
import wx
import wx.py.dispatcher as dp
import numpy as np
import pandas as pd
import zmq
import propgrid as pg
from bsmutility.bsmxpm import open_svg, run_svg, run_grey_svg, pause_svg, pause_grey_svg, \
                              stop_svg, stop_grey_svg
from bsmutility.utility import svg_to_bitmap
from bsmutility.pymgr_helpers import Gcm
from bsmutility.utility import build_tree
from bsmutility.fileviewbase import TreeCtrlNoTimeStamp, PanelNotebookBase, FileViewBase
from bsmutility.signalselsettingdlg import PropSettingDlg

def flatten(dictionary, parent_key='', separator='.'):
    items = []
    for key, value in dictionary.items():
        new_key = parent_key + separator + key if parent_key else key
        if isinstance(value, MutableMapping):
            items.extend(flatten(value, new_key, separator=separator).items())
        else:
            if isinstance(value, list):
                if len(value) == 1:
                    items.append((new_key, value))
                else:
                    for i, v in enumerate(value):
                        items.append((f'{new_key}[{i}]', v))
            else:
                items.append((new_key, value))
    return dict(items)

class ZMQLogger:
    def __init__(self, qresp):
        self.qresp = qresp

    def write(self, buf):
        self.qresp.put({'cmd': 'write_out', 'important': True, 'value': buf})

    def flush(self):
        pass

class ZMQMessage:
    def __init__(self, ipaddr, qcmd, qresp):
        self.qcmd = qcmd
        self.qresp = qresp
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.ipaddr = None
        self.connect(ipaddr)
        self.running = False

    def disconnect(self):
        if self.ipaddr:
            self.socket.disconnect(self.ipaddr)
        self.ipaddr = None

    def connect(self, ipaddr):
        self.disconnect()

        self.ipaddr = ipaddr
        self.socket.connect(ipaddr)
        self.socket.subscribe("")

    def receive(self):
        try:
            s = self.socket.recv_string(zmq.NOBLOCK)
            self.qresp.put({'cmd': 'data', 'value': s})
        except zmq.ZMQError:
            wx.Sleep(0.1)
        except Queue.Full:
            wx.Sleep(0.1)

    def process(self):
        # wait 1s and try to get some data, so the client can populate the data tree
        wx.Sleep(1)
        for i in range(5):
            self.receive()

        is_exit = False
        while not is_exit:
            if self.socket.closed or self.running:
                try:
                    cmd = self.qcmd.get_nowait()
                except Queue.Empty:
                    cmd = {}
            else:
                cmd = self.qcmd.get()
            command = cmd.get("cmd", '')
            if command:
                if command == "pause":
                    self.running = False
                elif command == "start":
                    self.running = True
                elif command == "stop":
                    self.running = False
                    self.disconnect()
                elif command == "connect":
                    self.disconnect()
                    ipaddr = cmd.get('ipaddr', '')
                    if ipaddr:
                        self.connect(ipaddr)
                elif command == "exit":
                    self.disconnect()
                    self.running = False
                    is_exit = True
                resp = cmd
                resp['value'] = True
                self.qresp.put(resp)
                continue
            if self.running:
                self.receive()

def zmq_process(ipaddr, qresp, qcmd, debug=False):
    if not debug:
        log = ZMQLogger(qresp)
        stdout = sys.stdout
        stderr = sys.stderr
        sys.stdout = log
        sys.stderr = log
    proc = ZMQMessage(ipaddr, qcmd, qresp)
    # infinite loop
    proc.process()
    if not debug:
        sys.stdout = stdout
        sys.stderr = stderr

class ZMQTree(TreeCtrlNoTimeStamp):

    def __init__(self, *args, **kwargs):
        TreeCtrlNoTimeStamp.__init__(self, *args, **kwargs)
        self.df = collections.deque(maxlen=1000)
        self.num = 0
        dp.connect(self.RetrieveData, 'zmqs.retrieve')
        self.last_updated_time = datetime.datetime.now()
        self._graph_retrieved = True

    def RetrieveData(self, num, path):
        self._graph_retrieved = True
        if num != self.num:
            return None, None
        y = self.GetItemDataFromPath(path)
        if y is None:
            return None, None
        x = None
        if self.x_path:
            x = self.GetItemDataFromPath(self.x_path)
        if x is None or len(x) != len(y):
            x = np.arange(0, len(y))
        return x, y

    def Load(self, data):
        # flatten the tree, so make it easy to combine multiple frames together
        # e.g., frame 1: {'a': [1, 2, 3]}, frame 2 {'a': [1, 2, 3]}, after
        # combination, it shall become {'a[0]': [1, 1], 'a[1]': [2, 2], 'a[3]': [3, 3]}
        data_f = flatten(data)
        super().Load(build_tree(data_f))
        self.df.append(data_f)

    def SetQueueMaxLen(self, maxlen):
        if maxlen != self.df.maxlen:
            df = collections.deque(maxlen=maxlen)
            for d in self.df:
                df.append(d)
            self.df = df

    def Update(self, data):
        if not self.data:
            self.Load(data)
        else:
            data_f = flatten(data)
            self.df.append(data_f)
            now = datetime.datetime.now()
            if self._graph_retrieved and (now - self.last_updated_time).seconds > 1:
                # notify the graph
                self._graph_retrieved = False
                self.last_updated_time = now
                wx.CallAfter(dp.send, 'graph.data_updated')

    def GetItemKeyFromPath(self, path):
        # the path shall be joined with '.', and the only exception is array
        # item, e.g., ['a', '0'] -> 'a[0]'
        tmp = [path[0]]
        for p in path[1:]:
            if re.match(r'(\[\d+\])+', p):
                tmp[-1] += p
            else:
                tmp.append(p)

        key = '.'.join(tmp)
        return key

    def GetItemDataFromPath(self, path):
        key = self.GetItemKeyFromPath(path)
        data = [d[key] if key in d else np.nan for d in self.df]
        return np.array(data)

    def GetItemPlotData(self, item):
        y = self.GetItemData(item)

        x = None
        if self.x_path is not None and self.GetItemPath(item) != self.x_path:
            x = self.GetItemDataFromPath(self.x_path)
            if len(x) != len(y):
                name = self.GetItemText(item)
                print(f"'{name}' and '{self.x_path[-1]}' have different length, ignore x-axis data!")
                x = None
        if x is None:
            x = np.arange(0, len(y))
        return x, y

    def GetItemDragData(self, item):
        pass

    def PlotItem(self, item, confirm=True):
        line = super().PlotItem(item, confirm=confirm)
        if line is not None:
            path = self.GetItemPath(item)
            line.trace_signal = ["zmqs.retrieve", self.num, path]
            line.autorelim = True
        self._graph_retrieved = True


class ZMQPanel(PanelNotebookBase):
    Gcc = Gcm()
    ID_RUN = wx.NewIdRef()
    ID_PAUSE = wx.NewIdRef()
    ID_STOP = wx.NewIdRef()

    def __init__(self, parent, filename=None):
        PanelNotebookBase.__init__(self, parent, filename=filename)

        self.Bind(wx.EVT_TEXT, self.OnDoSearch, self.search)

        self.zmq_status = "stop"
        self._cmd_id = 0
        self.zmq = None
        self.qcmd = None
        self.qresp = None
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)
        self.timer.Start(5)
        self.settings = {'protocol': 'tcp://', 'address': 'localhost', 'port': 2967, 'format': 'json', 'maxlen': 1024}
        self.settings.update(self.LoadSettings())

        self.tree.num = self.num

    @classmethod
    def LoadSettings(cls):
        resp = dp.send('frame.get_config', group='zmqs', key='settings')
        if resp and resp[0][1] is not None:
            return resp[0][1]
        return {}

    def init_toolbar(self):
        self.tb.AddTool(self.ID_OPEN, "Open",  svg_to_bitmap(open_svg, win=self),
                        wx.NullBitmap, wx.ITEM_NORMAL, "Open")
        self.tb.AddSeparator()
        self.tb.AddTool(self.ID_RUN, "Start", svg_to_bitmap(run_svg, win=self),
                        svg_to_bitmap(run_grey_svg, win=self), wx.ITEM_NORMAL,
                        "Start the ZMQ subscriber")
        self.tb.AddTool(self.ID_PAUSE, "Pause", svg_to_bitmap(pause_svg, win=self),
                        svg_to_bitmap(pause_grey_svg, win=self), wx.ITEM_NORMAL,
                        "Pause the ZMQ subscriber")
        #self.tb.AddTool(self.ID_STOP, "Stop", svg_to_bitmap(stop_svg, win=self),
        #                svg_to_bitmap(stop_grey_svg, win=self), wx.ITEM_NORMAL,
        #                "Stop the ZMQ subscriber")
    def init_pages(self):
        # data page
        panel, self.search, self.tree = self.CreatePageWithSearch(ZMQTree)
        self.notebook.AddPage(panel, 'Data')

    def OnTimer(self, event):
        try:
            # process the response
            self.process_response()
        except:
            traceback.print_exc(file=sys.stdout)

    def Destroy(self):
        self.timer.Stop()
        self.stop()
        super().Destroy()

    def process_response(self):
        if not self.qresp:
            return None
        try:
            # process the response
            resp = self.qresp.get_nowait()
            if resp:
                return self._process_response(resp)
        except Queue.Empty:
            pass
        return None

    def _process_response(self, resp):
        command = resp.get('cmd', '')
        if not command:
            return None
        value = resp.get('value', False)
        if command == 'data':
            # fmt = self.settings.get('format', 'json')
            self.tree.Update(json.loads(value))
        elif command in ['start', 'pause', 'stop']:
            if value:
                self.zmq_status = command
            if command in ['pause', 'stop']:
                # update the graph
                dp.send('graph.data_updated')
        return value

    def _send_command(self, cmd, **kwargs):
        """
        send the command to the simulation process

        don't call this function directly unless you know what it is doing.
        """
        try:
            if not self.zmq or not self.zmq.is_alive():
                print("The zmq subscriber has not started or is not alive!")
                return False
            # always increase the command ID
            cid = self._cmd_id
            self._cmd_id += 1
            # return, if the previous call has not finished
            # it may happen when the previous command is waiting for response,
            # and another command is sent (by clicking a button)
            if self.qresp is None or self.qcmd is None or self.zmq is None:
                raise KeyboardInterrupt
            block = kwargs.get('block', True)

            if not kwargs.get('silent', True):
                print(cmd, cid, kwargs)

            self.qcmd.put({'id': cid, 'cmd': cmd, 'arguments': kwargs})
            rtn = self.zmq.is_alive()
            self.timer.Stop()
            if block is True:
                # wait for the command to finish
                while self.zmq.is_alive():
                    try:
                        resp = self.qresp.get(timeout=0.3)
                    except Queue.Empty:
                        continue
                    wx.YieldIfNeeded()
                    # send the EVT_UPDATE_UI events so the UI status has a chance to
                    # update (e.g., menubar, toolbar)
                    wx.EventLoop.GetActive().ProcessIdle()
                    rtn = self._process_response(resp)
                    if resp.get('id', -1) == cid:
                        break
        except:
            traceback.print_exc(file=sys.stdout)
        self.timer.Start(5)
        return rtn

    def stop(self):
        """destroy the simulation"""
        if self.qresp is None or self.qcmd is None or self.zmq is None:
            return
        # stop the simulation kernel. No block operation allowed since
        # no response from the subprocess
        self._send_command('exit', block=False)
        #while not self.qresp.empty():
        #    self.qresp.get_nowait()
        self.zmq.join()
        self.zmq = None
        # stop the client
        self._process_response({'cmd': 'exit'})

    def start(self):
        """create an empty simulation"""

        filename = self.GetIPAddress()
        self.stop()
        self.qresp = mp.Queue(100)
        self.qcmd = mp.Queue()
        self.zmq = mp.Process(target=zmq_process, args=(filename, self.qresp, self.qcmd, True))
        self.zmq.start()

    def GetIPAddress(self):
        s = self.settings
        filename = f"{s['protocol']}{s['address']}:{s['port']}"
        return filename

    def Load(self, filename, add_to_history=True):
        """start the ZMQ subscriber"""
        if isinstance(filename, str):
            filename = json.loads(filename)
        if not isinstance(filename, dict) or 'protocol' not in filename or \
           'address' not in filename or 'port' not in filename:
            print('Invalid server settings: {filename}')
            return
        self.settings.update(filename)
        self.tree.SetQueueMaxLen(self.settings['maxlen'])

        resp = dp.send('frame.set_config', group='zmqs', settings=self.settings)
        if resp and resp[0][1] is not None:
            self.settings = resp[0][1]
        filename = self.GetIPAddress()
        self.start()
        super().Load(filename, add_to_history=False)

    def OnDoSearch(self, evt):
        pattern = self.search.GetValue()
        self.tree.Fill(pattern)
        item = self.tree.FindItemFromPath(self.tree.x_path)
        if item:
            self.tree.SetItemBold(item, True)
        self.search.SetFocus()

    def GetCaption(self):
        return self.filename

    @classmethod
    def GetSettings(cls, parent, settings=None):
        fmt = ['json']#, 'pyobj', 'bson', 'cbor', 'cdr', 'msgpack', 'protobuf', 'ros1']
        props = [pg.PropChoice(['tcp://', 'ipc://', 'pgm://', 'udp://', 'inproc://'])
                   .Label('Protocol').Name('protocol').Value('tcp://'),
                 pg.PropText().Label('Address').Name('address').Value('localhost'),
                 pg.PropInt().Label('Port').Name('port').Value(2967),
                 pg.PropChoice(fmt).Label('Message Format').Name('format').Value('json'),
                 pg.PropInt().Label('Buffer Size').Name('maxlen').Value(1024)]

        dlg = PropSettingDlg(parent, props, config='zmqs.settings')
        if dlg.ShowModal() == wx.ID_OK:
            setting = dlg.GetSettings()
            return setting
        return None

    def OnProcessCommand(self, event):
        """process the menu command"""
        eid = event.GetId()
        if eid == self.ID_OPEN:
            ipaddr = self.GetSettings(self, self.settings)
            if ipaddr is not None:
                self.Load(filename=ipaddr)
                title = self.GetCaption()
                dp.send('frame.set_panel_title', pane=self, title=title)
        elif eid == self.ID_RUN:
            self._send_command('start', block=False)
        elif eid == self.ID_PAUSE:
            self._send_command('pause', block=False)
        elif eid == self.ID_STOP:
            self._send_command('stop', block=False)
        else:
            super().OnProcessCommand(event)

    def OnUpdateCmdUI(self, event):
        eid = event.GetId()
        if eid == self.ID_RUN:
            event.Enable(self.zmq and self.zmq.is_alive() and self.zmq_status != 'start')
        elif eid == self.ID_PAUSE:
            event.Enable(self.zmq and self.zmq.is_alive() and self.zmq_status == 'start')
        else:
            super().OnUpdateCmdUI(event)

class ZMQ(FileViewBase):
    name = 'ZMQ'
    panel_type = ZMQPanel

    @classmethod
    def check_filename(cls, filename):
        if filename is None:
            return True
        if isinstance(filename, dict):
            return filename.get('protocol', 'tcp://').startswith('tcp')
        if isinstance(filename, str):
            return filename.startswith('tcp')
        return False
    @classmethod
    def initialized(cls):
        # add mat to the shell
        dp.send(signal='shell.run',
                command='from bsmplot.bsm.zmqs import ZMQ',
                prompt=False,
                verbose=False,
                history=False)
    @classmethod
    def process_command(cls, command):
        if command == cls.IDS.get('open', None):

            ipaddress = cls.panel_type.GetSettings(cls.frame)
            if ipaddress is not None:
                cls.open(filename=ipaddress, activate=True)
        else:
            super().process_command(command)

    @classmethod
    def get(cls, num=None, filename=None, data_only=True):
        manager = super().get(num, filename, data_only)
        data = None
        if manager:
            df = manager.tree.df
            if len(df) == 0:
                return data
            keys = df[0].keys()
            data = {}
            for k in keys:
                data[k] = [d[k] if k in d else np. nan for d in df]
            data = build_tree(pd.DataFrame(data))
        return data

    @classmethod
    def get_menu(cls):
        return [['open', f'File:Open:{cls.name} subscriber']]

def bsm_initialize(frame, **kwargs):
    ZMQ.initialize(frame)
