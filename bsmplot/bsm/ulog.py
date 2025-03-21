import sys
import os
import traceback
import wx
import wx.py.dispatcher as dp
import pyulog
import numpy as np
import pandas as pd
from bsmutility.pymgr_helpers import Gcm
from bsmutility.fileviewbase import ListCtrlBase, TreeCtrlWithTimeStamp, PanelNotebookBase, FileViewBase
from bsmutility.utility import build_tree

def load_ulog(filename):
    ulg = pyulog.ULog(filename)

    data = {}
    for d in ulg.data_list:
        df = pd.DataFrame(d.data)
        data[d.name] = df
    data = build_tree(data)
    t = [m.timestamp for m in ulg.logged_messages]
    m = [m.message for m in ulg.logged_messages]
    l = [m.log_level_str() for m in ulg.logged_messages]
    log = pd.DataFrame.from_dict({'timestamp': t, 'level': l, "message": m})

    info = pd.DataFrame.from_dict({'key': ulg.msg_info_dict.keys(),
                                   'value': ulg.msg_info_dict.values()})
    info = info.sort_values(by=['key'], ignore_index=True)
    param = ulg.initial_parameters

    changed_param = pd.DataFrame.from_records(ulg.changed_parameters, columns=['timestamp', 'key', 'value'])
    return {'data': data, 'log': log, 'info': info, 'param': param,
            'changed_param': changed_param}

class ULogTree(TreeCtrlWithTimeStamp):

    def GetItemPlotData(self, item):
        x, y = super().GetItemPlotData(item)
        if (x is not None) and np.all(x == self.GetItemTimeStamp(item)):
            # convert timestamp from us to s
            x = x/1e6
        return x, y

class MessageListCtrl(ListCtrlBase):

    def BuildColumns(self):
        super().BuildColumns()
        start = self.data_start_column
        self.InsertColumn(start, "Timestamp", width=120)
        self.InsertColumn(start+1, "Type", width=120)
        self.InsertColumn(start+2, "Message", width=wx.LIST_AUTOSIZE_USEHEADER)

    def FindText(self, start, end, text, flags=0):
        direction = 1 if end > start else -1
        for i in range(start, end+direction, direction):
            m = self.data_shown.iloc[i].message
            if self.Search(m, text, flags):
                return i

        # not found
        return -1

    def ApplyPattern(self):
        if not self.pattern:
            self.data_shown = self.data
        else:
            self.data_shown = self.data.loc[self.data.level.str.contains(self.pattern, case=False) | self.data.message.str.contains(self.pattern, case=False)]

    def OnGetItemText(self, item, column):
        if column < self.data_start_column:
            return super().OnGetItemText(item, column)
        column -= self.data_start_column
        m = self.data_shown.iloc[item]
        if column == 0:
            return str(m.timestamp/1e6)
        if column == 1:
            return m.level
        if column == 2:
            return m.message
        return ""

class InfoListCtrl(ListCtrlBase):

    def BuildColumns(self):
        super().BuildColumns()
        start = self.data_start_column
        self.InsertColumn(start, "Key", width=120)
        self.InsertColumn(start+1, "Value", width=wx.LIST_AUTOSIZE_USEHEADER)

    def FindText(self, start, end, text, flags=0):
        direction = 1 if end > start else -1
        for i in range(start, end+direction, direction):
            m = self.data_shown.iloc[i]
            if self.Search(m['key'], text, flags) or self.Search(str(m['value']), text, flags):
                return i

        # not found
        return -1

    def OnGetItemText(self, item, column):
        if column < self.data_start_column:
            return super().OnGetItemText(item, column)
        column -= self.data_start_column
        m = self.data_shown.iloc[item]
        if column == 0:
            return str(m.key)
        if column == 1:
            return str(m.value)
        return ""

    def ApplyPattern(self):
        if not self.pattern:
            self.data_shown = self.data
        else:
            self.data_shown = self.data.loc[self.data.key.str.contains(self.pattern, case=False) | self.data.value.str.contains(self.pattern, case=False)]

class ParamListCtrl(ListCtrlBase):

    def BuildColumns(self):
        super().BuildColumns()
        start = self.data_start_column
        self.InsertColumn(start, "Key", width=200)
        self.InsertColumn(start+1, "Value", width=wx.LIST_AUTOSIZE_USEHEADER)

    def FindText(self, start, end, text, flags=0):
        direction = 1 if end > start else -1
        for i in range(start, end+direction, direction):
            m = self.data_shown[i]
            if self.Search(str(m[0]), text, flags) or self.Search(str(m[1]), text, flags):
                return i

        # not found
        return -1

    def ApplyPattern(self):
        if self.pattern:
            self.data_shown = [[k, v] for k, v in self.data.items() if self.pattern in str(k).lower() or self.pattern.lower() in str(v).lower()]
        else:
            self.data_shown = [[k, v] for k, v in self.data.items()]

        self.data_shown = sorted(self.data_shown, key=lambda x: x[0])

    def OnGetItemText(self, item, column):
        if column < self.data_start_column:
            return super().OnGetItemText(item, column)
        column -= self.data_start_column
        return str(self.data_shown[item][column])

class ChgParamListCtrl(ListCtrlBase):

    def BuildColumns(self):
        super().BuildColumns()
        start = self.data_start_column
        self.InsertColumn(start, "Timestamp", width=120)
        self.InsertColumn(start+1, "Key", width=200)
        self.InsertColumn(start+2, "Value", width=wx.LIST_AUTOSIZE_USEHEADER)

    def FindText(self, start, end, text, flags=0):
        direction = 1 if end > start else -1
        for i in range(start, end+direction, direction):
            m = self.data_shown[i]
            if self.Search(str(m[1]), text, flags) or self.Search(str(m[2]), text, flags):
                return i

        # not found
        return -1

    def OnGetItemText(self, item, column):
        if column < self.data_start_column:
            return super().OnGetItemText(item, column)
        column -= self.data_start_column
        m = self.data_shown.iloc[item]
        if column == 0:
            return str(m.timestamp/1e6)
        if column == 1:
            return str(m.key)
        if column == 2:
            return str(m.value)
        return ""

    def ApplyPattern(self):
        if not self.pattern:
            self.data_shown = self.data
        else:
            self.data_shown = self.data.loc[self.data.key.str.contains(self.pattern, case=False) | self.data.value.astype(str).str.contains(self.pattern, case=False)]


class ULogPanel(PanelNotebookBase):
    Gcc = Gcm()

    def __init__(self, parent, filename=None):
        self.ulg = None
        PanelNotebookBase.__init__(self, parent, filename=filename)

        self.Bind(wx.EVT_TEXT, self.OnDoSearch, self.search)
        self.Bind(wx.EVT_TEXT, self.OnDoSearchLog, self.search_log)
        self.Bind(wx.EVT_TEXT, self.OnDoSearchInfo, self.search_info)
        self.Bind(wx.EVT_TEXT, self.OnDoSearchParam, self.search_param)
        self.Bind(wx.EVT_TEXT, self.OnDoSearchChgParam, self.search_chg_param)

    def init_pages(self):
        # data page
        panel, self.search, self.tree = self.CreatePageWithSearch(ULogTree)
        self.notebook.AddPage(panel, 'Data')
        # log page
        panel_log, self.search_log, self.logList = self.CreatePageWithSearch(MessageListCtrl)
        self.notebook.AddPage(panel_log, 'Log')

        panel_info, self.search_info, self.infoList = self.CreatePageWithSearch(InfoListCtrl)
        self.notebook.AddPage(panel_info, 'Info')

        panel_param, self.search_param, self.paramList = self.CreatePageWithSearch(ParamListCtrl)
        self.notebook.AddPage(panel_param, 'Param')

        panel_chg_param, self.search_chg_param, self.chgParamList = self.CreatePageWithSearch(ChgParamListCtrl)
        self.notebook.AddPage(panel_chg_param, 'Changed Param')

        self.ulg = None

    def doLoad(self, filename, add_to_history=True, data=None):
        """load the ulog file"""
        u = data
        if u is None:
            u = self.open(filename)
        self.ulg = u
        if u:
            self.tree.Load(u['data'], filename)
            self.logList.Load(u['log'])
            self.infoList.Load(u['info'])
            self.paramList.Load(u['param'])
            self.chgParamList.Load(u['changed_param'])
        else:
            self.tree.Load(None)
            self.logList.Load(None)
            self.infoList.Load(None)
            self.paramList.Load(None)
            self.chgParamList.Load(None)
            add_to_history = False

        super().doLoad(filename, add_to_history=add_to_history, data=data)

    def OnDoSearch(self, evt):
        pattern = self.search.GetValue()
        self.tree.Fill(pattern)
        self.search.SetFocus()

    def OnDoSearchLog(self, evt):
        pattern = self.search_log.GetValue()
        self.logList.Fill(pattern)

    def OnDoSearchInfo(self, evt):
        pattern = self.search_info.GetValue()
        self.infoList.Fill(pattern)

    def OnDoSearchParam(self, evt):
        pattern = self.search_param.GetValue()
        self.paramList.Fill(pattern)

    def OnDoSearchChgParam(self, evt):
        pattern = self.search_chg_param.GetValue()
        self.chgParamList.Fill(pattern)

    @classmethod
    def GetFileType(cls):
        return "ulog files (*.ulg;*.ulog)|*.ulg;*.ulog|All files (*.*)|*.*"

    @classmethod
    def do_open(cls, filename):
        return load_ulog(filename)


class ULog(FileViewBase):
    name = 'ulog'
    panel_type = ULogPanel

    @classmethod
    def check_filename(cls, filename):
        if not super().check_filename(filename):
            return False

        if filename is None:
            return True
        _, ext = os.path.splitext(filename)
        return (ext.lower() in ['.ulog', '.ulg'])

    @classmethod
    def initialized(cls):
        # add ulog to the shell
        dp.send(signal='shell.run',
                command='from bsmplot.bsm.ulog import ULog as ulog',
                prompt=False,
                verbose=False,
                history=False)

    @classmethod
    def get(cls, num=None, filename=None, data_only=True):
        manager = super().get(num, filename, data_only)
        ulg = None
        if manager:
            ulg = manager.ulg
        elif filename:
            try:
                ulg = load_ulog(filename)
            except:
                traceback.print_exc(file=sys.stdout)
        if ulg:
            data = ulg
            if data_only and data:
                return data.get('data', None)
            return data
        return None

def bsm_initialize(frame, **kwargs):
    ULog.initialize(frame)
