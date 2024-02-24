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
from bsmutility.utility import build_tree, get_tree_item_name
from propgrid import PropText, PropChoice, PropSeparator
from .quaternion import Quaternion

def load_ulog(filename):
    try:
        ulg = pyulog.ULog(filename)
    except:
        traceback.print_exc(file=sys.stdout)
        return {}

    data = {}
    for d in ulg.data_list:
        df = pd.DataFrame(d.data)
        data[d.name] = df
    data = build_tree(data)
    t = [m.timestamp for m in ulg.logged_messages]
    m = [m.message for m in ulg.logged_messages]
    l = [m.log_level_str() for m in ulg.logged_messages]
    log = pd.DataFrame.from_dict({'timestamp': t, 'level': l, "message": m})
    info = ulg.msg_info_dict
    param = ulg.initial_parameters
    changed_param = ulg.changed_parameters
    return {'data': data, 'log': log, 'info': info, 'param': param,
            'changed_param': changed_param}

class ULogTree(TreeCtrlWithTimeStamp):

    ID_QUATERNION_RPY = wx.NewIdRef()
    ID_RAD_TO_DEG = wx.NewIdRef()
    ID_DEG_TO_RAD = wx.NewIdRef()

    def GetItemMenu(self, item):
        menu = super().GetItemMenu(item)
        if menu is None:
            return None
        if not self.ItemHasChildren(item):
            menu.Append(self.ID_QUATERNION_RPY, 'Quaternion to Roll/Pitch/Yaw')
            menu.Append(self.ID_RAD_TO_DEG, 'Radian to degree')
            menu.Append(self.ID_DEG_TO_RAD, 'Degree to radian')
        return menu

    def GetItemPlotData(self, item):
        x, y = super().GetItemPlotData(item)
        if x is not None:
            # convert us to s
            x = x/1e6
        return x, y

    def GetItemDragData(self, item):
        data = super().GetItemDragData(item)
        if self.timestamp_key in data:
            data[self.timestamp_key] /= 1e6
        return data

    def GetPlotXLabel(self):
        return "t(s)"

    def Quaternion2YPR(self, paths=None, item=None):
        start = ''
        config = 'ulog.quaternion'
        name = '~'
        if item is not None and item.IsOk() and self.ItemHasChildren(item):
            path = self.GetItemPath(item)
            start = get_tree_item_name(path)
            config += ".".join(path)

        additional = [PropSeparator().Label('Output'),
                      PropChoice(['Degree', 'Radian']).Label('Format')
                                 .Name('format').Value('Degree'),
                      PropText().Label("Name").Name('name').Value(name)]
        values = None
        if paths is not None and len(paths) == 4:
            valid_paths = True
            if start:
                for i, p in enumerate(paths):
                    if not p.startswith(start):
                        valid_paths = False
                        break
                    # remove '{start}.'
                    paths[i] = p[len(start)+1:]

            if valid_paths:
                values = {'w': paths[0], 'x': paths[1],
                          'y': paths[2], 'z': paths[3]}
        df_in, settings = self.SelectSignal(items=['w', 'x', 'y', 'z'],
                                            values=values,
                                            config=config,
                                            additional = additional,
                                            start=start)
        if df_in is not None:
            q = Quaternion(df_in['w'], df_in['x'], df_in['y'], df_in['z']).to_angle()
            radian = settings['format'] == 'Radian'
            df = pd.DataFrame()
            df['yaw'] = q[0] if not radian else np.deg2rad(q[0])
            df['pitch'] = q[1] if not radian else np.deg2rad(q[1])
            df['roll'] = q[2] if not radian else np.deg2rad(q[2])
            if start:
                # add columns to same DataFrame
                data = self.GetItemData(item)
                name = settings.get('name', '')
                data[f'{name}yaw'] = df['yaw']
                data[f'{name}pitch'] = df['pitch']
                data[f'{name}roll'] = df['roll']
                self.RefreshChildren(item)
                path = self.GetItemPath(item)
                new_item = self.FindItemFromPath(path+[f'{name}yaw'])
                if new_item and new_item.IsOk():
                    self.EnsureVisible(new_item)
                    self.SetFocusedItem(new_item)
            else:
                self.UpdateData({settings.get('name', 'ypr'): df})

    def ConvertRad2Deg(self, item):
        if item is None or not item.IsOk():
            return None
        # convert an item, insert it to the same DataFrame
        name = self.GetItemText(item)
        return self.ConvertItem(item, equation='np.rad2deg(#)',name=f'{name}_deg')

    def ConvertDeg2Rad(self, item):
        if item is None or not item.IsOk():
            return None
        # convert an item, insert it to the same DataFrame
        name = self.GetItemText(item)
        return self.ConvertItem(item, equation='np.rad2deg(#)', name=f'{name}_rad')

    def OnProcessCommand(self, cmd, item):
        selections = []
        for item in self.GetSelections():
            selections.append(get_tree_item_name(self.GetItemPath(item)))

        if cmd == self.ID_QUATERNION_RPY:
            parent = self.GetItemParent(item)
            self.Quaternion2YPR(paths=selections, item=parent)

        elif cmd == self.ID_RAD_TO_DEG:
            self.ConvertRad2Deg(item=item)

        elif cmd == self.ID_DEG_TO_RAD:
            self.ConvertDeg2Rad(item=item)
        else:
            super().OnProcessCommand(cmd, item)

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
            m = self.data_shown[i]
            if self.Search(m[0], text, flags) or self.Search(str(m[1]), text, flags):
                return i

        # not found
        return -1

    def Load(self, data):
        data = [[k, v] for k, v in data.items()]
        data = sorted(data, key=lambda x: x[0])
        super().Load(data)

    def OnGetItemText(self, item, column):
        if column < self.data_start_column:
            return super().OnGetItemText(item, column)
        column -= self.data_start_column
        return str(self.data_shown[item][column])

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
        m = self.data_shown[item]
        if column == 0:
            return str(m[0]/1e6)
        return str(m[column])


class ULogPanel(PanelNotebookBase):
    Gcc = Gcm()

    def __init__(self, parent, filename=None):
        self.ulg = None
        PanelNotebookBase.__init__(self, parent, filename=filename)

        self.Bind(wx.EVT_TEXT, self.OnDoSearch, self.search)
        self.Bind(wx.EVT_TEXT, self.OnDoSearchLog, self.search_log)
        self.Bind(wx.EVT_TEXT, self.OnDoSearchParam, self.search_param)

    def init_pages(self):
        # data page
        panel, self.search, self.tree = self.CreatePageWithSearch(ULogTree)
        self.notebook.AddPage(panel, 'Data')
        # log page
        panel_log, self.search_log, self.logList = self.CreatePageWithSearch(MessageListCtrl)
        self.notebook.AddPage(panel_log, 'Log')

        self.infoList = InfoListCtrl(self.notebook)
        self.notebook.AddPage(self.infoList, 'Info')

        panel_param, self.search_param, self.paramList = self.CreatePageWithSearch(ParamListCtrl)
        self.notebook.AddPage(panel_param, 'Param')

        self.chgParamList = ChgParamListCtrl(self.notebook)
        self.notebook.AddPage(self.chgParamList, 'Changed Param')

        self.ulg = None

    def Load(self, filename, add_to_history=True):
        """load the ulog file"""
        u = load_ulog(filename)
        self.ulg = u
        if u:
            self.tree.Load(u['data'])
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

        super().Load(filename, add_to_history=add_to_history)

    def OnDoSearch(self, evt):
        pattern = self.search.GetValue()
        self.tree.Fill(pattern)
        self.search.SetFocus()

    def OnDoSearchLog(self, evt):
        pattern = self.search_log.GetValue()
        self.logList.Fill(pattern)

    def OnDoSearchParam(self, evt):
        pattern = self.search_param.GetValue()
        self.paramList.Fill(pattern)

    @classmethod
    def GetFileType(cls):
        return "ulog files (*.ulg;*.ulog)|*.ulg;*.ulog|All files (*.*)|*.*"

class ULog(FileViewBase):
    name = 'ulog'
    panel_type = ULogPanel

    @classmethod
    def check_filename(cls, filename):
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
