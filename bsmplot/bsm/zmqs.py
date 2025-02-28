import os
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
                              stop_svg, stop_grey_svg, more_svg, saveas_svg, download_svg, \
                              upload_svg

from bsmutility.utility import svg_to_bitmap
from bsmutility.pymgr_helpers import Gcm
from bsmutility.utility import build_tree, get_tree_item_name
from bsmutility.fileviewbase import TreeCtrlNoTimeStamp, PanelNotebookBase, FileViewBase
from bsmutility.signalselsettingdlg import PropSettingDlg
from bsmutility.richdialog import RichNumberEntryDialog
from bsmutility.surface import SurfacePanel

def flatten(dictionary, parent_key='', separator='.'):
    items = []
    for key, value in dictionary.items():
        new_key = parent_key + separator + key if parent_key else key
        if isinstance(value, MutableMapping):
            items.extend(flatten(value, new_key, separator=separator).items())
        else:
            if isinstance(value, list):
                try:
                    v = np.asarray(value)
                    if np.issubdtype(v.dtype, np.number) and (v.ndim > 1):
                        value = v
                except:
                    pass
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
    def __init__(self, ipaddr, qcmd, qresp, fmt='json'):
        self.qcmd = qcmd
        self.qresp = qresp
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)

        self.fmt = fmt
        self.serialize_zmq = None
        self.receive_zmq = self.socket.recv
        try:
            if fmt == 'bson':
                import bson
                self.serialize_zmq = bson.loads
            elif fmt == 'cbor':
                import cbor2
                self.serialize_zmq = cbor2.loads
            elif fmt == 'msgpack':
                import msgpack
                self.serialize_zmq = msgpack.unpackb
            else:
                self.receive_zmq = self.socket.recv_string
                self.serialize_zmq = json.loads
        except:
            traceback.print_exc()
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
        for i in range(10):
            # wait 200,s and try to get some data, so the client can populate
            # the data tree
            if self.receive(sleep_ms=200):
                break

    def receive(self, sleep_ms=100):
        try:
            s = self.receive_zmq(zmq.NOBLOCK)
            if self.serialize_zmq is not None:
                data = self.serialize_zmq(s)
                self.qresp.put({'cmd': 'data', 'value': data})
            return True
        except zmq.ZMQError:
            wx.MilliSleep(sleep_ms)
        except Queue.Full:
            wx.MilliSleep(sleep_ms)
        return False

    def process(self):
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

def zmq_process(ipaddr, qresp, qcmd, fmt, debug=False):
    if not debug:
        log = ZMQLogger(qresp)
        stdout = sys.stdout
        stderr = sys.stderr
        sys.stdout = log
        sys.stderr = log
    proc = ZMQMessage(ipaddr, qcmd, qresp, fmt)
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
        self._num_rx = 0
        self.exclude_keys = ['_frame_id']
        # minimal time (in s) to update plot
        self._data_update_gap = self.LoadConfig('data_update_gap', 1)

    def RetrieveData(self, num, path, **kwargs):
        self._graph_retrieved = True
        if num != self.num:
            return None, None, None
        since = kwargs.get('last_frame_id', -1)
        y = self._get_data_from_path(path, since=since)
        if y is None:
            return None, None, None
        x = None
        if self.x_path:
            x = self._get_data_from_path(self.x_path, since=since)
        if x is None or len(x) != len(y):
            x = np.arange(0, len(y))
        return x, y, self._num_rx

    def Load(self, data, filename=None):
        # flatten the tree, so make it easy to combine multiple frames together
        # e.g., frame 1: {'a': [1, 2, 3]}, frame 2 {'a': [1, 2, 3]}, after
        # combination, it shall become {'a[0]': [1, 1], 'a[1]': [2, 2], 'a[3]': [3, 3]}
        self.df.clear()
        data_f = {}
        if data is not None:
            data_f = flatten(data)
            self.df.append(data_f)
        elif isinstance(filename, str) and os.path.isfile(filename):
            with open(filename, "r") as ins:
                num_lines = sum(1 for _ in ins)
            with open(filename, "r") as ins:
                self.SetQueueMaxLen(num_lines)
                for line in ins:
                    try:
                        self.df.append(flatten(json.loads(line)))
                    except:
                        continue
            if len(self.df) > 0:
                data_f = self.df[0]
            else:
                print(f"Invalid or empty data file: {filename}")
        super().Load(build_tree(data_f), filename)

    def SetQueueMaxLen(self, maxlen):
        if maxlen != self.df.maxlen:
            df = collections.deque(maxlen=maxlen)
            for d in self.df:
                df.append(d)
            self.df = df

    def Update(self, data, filename=None):
        if isinstance(data, MutableMapping):
            self._num_rx += 1
            data['_frame_id'] = self._num_rx
        if not self.data:
            self.Load(data, filename)
        else:
            data_f = flatten(data)
            self.df.append(data_f)
            now = datetime.datetime.now()
            if self._graph_retrieved and (now - self.last_updated_time).total_seconds() >= self._data_update_gap:
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
        data = super().GetItemDataFromPath(path)
        if isinstance(data, MutableMapping):
            # folder to list children (get_children), just return
            return data

        return self._get_data_from_path(path)

    def _get_data_from_path(self, path, since=-1):
        # check if in converted item
        idx = [1, 0]
        name = get_tree_item_name(path)
        if name in self._converted_item:
            c = self._converted_item[name]
            idx = c[0]
            settings = c[1]
            data = self.doConvertFromSetting(settings)
            if idx[0] > 1 and data is not None:
                data = data[idx[1]]
            return data

        key = self.GetItemKeyFromPath(path)
        data = [d[key] if key in d else np.nan for d in self.df if d['_frame_id'] > since]
        data = np.array(data)
        return None if pd.isna(data).all() else data

    def PlotItem(self, item, confirm=True):
        line = super().PlotItem(item, confirm=confirm)
        if line is not None:
            path = self.GetItemPath(item)
            line.trace_signal = {'signal': "zmqs.retrieve", 'num': self.num, 'path':path}
            line.autorelim = True
        self._graph_retrieved = True

    def get(self, as_tree=True):
        data = None
        if len(self.df) == 0:
            return data
        keys = self.df[0].keys()
        data = {}
        for k in keys:
            data[k] = np.array([d[k] if k in d else np.nan for d in self.df])
        data = pd.DataFrame(data)
        if as_tree:
            data = build_tree(data)
        return data

    def SetDataUpdateGap(self, gap, save_as_default=False):
        self._data_update_gap = gap
        if save_as_default:
            self.SetConfig(data_update_gap = gap)

    def GetDataUpdateGap(self):
        return self._data_update_gap

    def plot(self, x, y, label, step=False):
        plt = super().plot(x, y, label, step=step)
        if isinstance(plt, SurfacePanel):
            plt.canvas.SetBufLen(256)
        return plt

class ZMQPanel(PanelNotebookBase):
    Gcc = Gcm()
    ID_RUN = wx.NewIdRef()
    ID_PAUSE = wx.NewIdRef()
    ID_STOP = wx.NewIdRef()
    ID_EXPORT_CSV = wx.NewIdRef()
    ID_EXPORT_JSON = wx.NewIdRef()
    ID_IMPORT_JSON = wx.NewIdRef()
    ID_SET_DATA_UPDATE_GAP = wx.NewIdRef()

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
        self.settings = {'protocol': 'tcp://', 'address': 'localhost', 'port': 2967,
                         'format': 'json', 'maxlen': 1024}
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
        self.tb.AddSeparator()
        self.tb.AddTool(self.ID_IMPORT_JSON, "Import", svg_to_bitmap(upload_svg, win=self),
                        wx.NullBitmap, wx.ITEM_NORMAL,
                        "Import the data from json list file")
        self.tb.AddSeparator()
        self.tb.AddTool(self.ID_EXPORT_JSON, "Export json list", svg_to_bitmap(download_svg, win=self),
                        wx.NullBitmap, wx.ITEM_NORMAL,
                        "Export the data to json list file")
        self.tb.AddTool(self.ID_EXPORT_CSV, "Export CSV", svg_to_bitmap(saveas_svg, win=self),
                        wx.NullBitmap, wx.ITEM_NORMAL,
                        "Export the data to csv file")
        self.tb.AddStretchSpacer()
        self.tb.AddTool(self.ID_MORE, "More", svg_to_bitmap(more_svg, win=self),
                        wx.NullBitmap, wx.ITEM_NORMAL, "More")

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
        self.stop()
        self.timer.Stop()
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
            self.tree.Update(value, self.GetCaption())
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
        # looks like none-blocking command + zmp.join() may not work when close
        # the panel (some kind of deadlock)
        self._send_command('exit', block=True)
        #while not self.qresp.empty():
        #    self.qresp.get_nowait()
        #self.zmq.join()
        self.zmq = None
        # stop the client
        self._process_response({'cmd': 'exit'})

    def start(self):
        """create an empty simulation"""

        filename = self.GetIPAddress()
        self.stop()
        self.qresp = mp.Queue(100)
        self.qcmd = mp.Queue()
        self.zmq = mp.Process(target=zmq_process, args=(filename, self.qresp, self.qcmd, self.settings['format'], True))
        self.zmq.start()

    def GetIPAddress(self):
        s = self.settings
        if 'protocol' in s and 'address' in s and 'port' in s:
            filename = f"{s['protocol']}{s['address']}:{s['port']}"
            return filename
        return None

    def Load(self, filename, add_to_history=True):
        """start the ZMQ subscriber"""
        if isinstance(filename, str):
            if not os.path.isfile(filename):
                try:
                    filename = json.loads(filename)
                except:
                    print('Invalid server settings: {filename}')
                    return
        if isinstance(filename, dict):
            if 'protocol' not in filename or 'address' not in filename or \
                'port' not in filename:
                print('Invalid server settings: {filename}')
                return
            self.settings.update(filename)
            self.tree.SetQueueMaxLen(self.settings['maxlen'])

            resp = dp.send('frame.set_config', group='zmqs', settings=self.settings)
            if resp and resp[0][1] is not None:
                self.settings = resp[0][1]
            self.start()
        else:
            self.tree.Load(data=None, filename=filename)
        super().Load(filename, add_to_history=False)

    def OnDoSearch(self, evt):
        pattern = self.search.GetValue()
        self.tree.Fill(pattern)
        item = self.tree.FindItemFromPath(self.tree.x_path)
        if item:
            self.tree.SetItemBold(item, True)
        self.search.SetFocus()

    def GetCaption(self):
        if isinstance(self.filename, str):
            return super().GetCaption()
        return self.GetIPAddress() or "unknown"

    @classmethod
    def GetSettings(cls, parent, settings=None):
        fmt = ['json']#, 'pyobj', 'bson', 'cbor', 'cdr', 'msgpack', 'protobuf', 'ros1']
        try:
            import bson
            fmt.append('bson')
        except:
            pass
        try:
            import cbor2
            fmt.append('cbor')
        except:
            pass
        try:
            import msgpack
            fmt.append('msgpack')
        except:
            pass
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
                dp.send('frame.set_panel_title', pane=self, title=title,
                        name=ipaddr)
        elif eid == self.ID_RUN:
            self._send_command('start', block=False)
        elif eid == self.ID_PAUSE:
            self._send_command('pause', block=False)
        elif eid == self.ID_STOP:
            self._send_command('stop', block=False)
        elif eid == self.ID_IMPORT_JSON:
            style = wx.FD_OPEN | wx.FD_CHANGE_DIR
            dlg = wx.FileDialog(self.GetTopLevelParent(),
                                'Open',
                                wildcard="All files (*.*)|*.*",
                                style=style)
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                self.Load(filename=path)
        elif eid == self.ID_EXPORT_JSON:
            style = wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT | wx.FD_CHANGE_DIR
            dlg = wx.FileDialog(self.GetTopLevelParent(),
                                'Save As',
                                wildcard="All files (*.*)|*.*",
                                style=style)
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                with open(path, 'w') as fp:
                    for line in self.tree.df:
                        try:
                            line = json.dumps(build_tree(line))
                        except:
                            continue
                        fp.write(f"{line}\n")
        elif eid == self.ID_EXPORT_CSV:
            style = wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT | wx.FD_CHANGE_DIR
            dlg = wx.FileDialog(self.GetTopLevelParent(),
                                'Save As',
                                wildcard="csv files (*.csv)|*.csv|All files (*.*)|*.*",
                                style=style)
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                df = self.tree.get(as_tree=False)
                if df is not None:
                    df.to_csv(path, index=False)
                else:
                    print('Invalid data')
        elif eid == self.ID_SET_DATA_UPDATE_GAP:
            msg = 'The minimal waiting time to notify the plot(s) to update:'
            parent = self.GetTopLevelParent()
            dlg = RichNumberEntryDialog(self, msg, 'time (ms)', 'Save the setting as default', parent.GetLabel(),
                                       int(self.tree.GetDataUpdateGap()*1000), 0, 10000)
            if dlg.ShowModal() == wx.ID_OK:
                self.tree.SetDataUpdateGap(dlg.GetValue()/1000, dlg.IsCheckBoxChecked())
        else:
            super().OnProcessCommand(event)

    def OnUpdateCmdUI(self, event):
        eid = event.GetId()
        if eid == self.ID_RUN:
            event.Enable(self.zmq is not None and self.zmq.is_alive() and self.zmq_status != 'start')
        elif eid == self.ID_PAUSE:
            event.Enable(self.zmq is not None and self.zmq.is_alive() and self.zmq_status == 'start')
        else:
            super().OnUpdateCmdUI(event)

    def GetMoreMenu(self):
        menu = super().GetMoreMenu()
        menu.AppendSeparator()

        menu.Append(self.ID_SET_DATA_UPDATE_GAP, 'Set the plot update period')
        return menu

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
        super().initialized()

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
            return manager.tree.get(as_tree=True)
        return data

    @classmethod
    def get_menu(cls):
        return [['open', f'File:Open:{cls.name} subscriber']]

def bsm_initialize(frame, **kwargs):
    ZMQ.initialize(frame)
