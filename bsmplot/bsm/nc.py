import os
import sys
import traceback
import wx
import wx.py.dispatcher as dp
import numpy as np
import pandas as pd
import netCDF4
from netCDF4 import Dataset
from bsmutility.pymgr_helpers import Gcm
from bsmutility.fileviewbase import TreeCtrlNoTimeStamp, ListCtrlBase, PanelNotebookBase, FileViewBase
from bsmutility.autocomplete import AutocompleteTextCtrl
from bsmutility.utility import get_tree_item_name

def load_nc(filename):
    data = {}
    attrs = {}
    nc = Dataset(filename)
    def _get_attr(v):
        attrs = {}
        for att in v.ncattrs():
            attrs[att] = v.getncattr(att)
        return attrs

    def _load_group(group):
        data = {}
        attrs = {}
        for k, v in group.variables.items():
            data[k] = np.asarray(v[:])
            attrs[k] = _get_attr(v)

        attrs['.'] = _get_attr(group)

        for g, v in group.groups.items():
            data[g], attrs[g] = _load_group(v)
        return data, attrs
    data, attrs = _load_group(nc)
    nc.close()
    return {'nc': data}, {'nc': attrs}

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


class AttrsDialog(wx.Dialog):
    def __init__(self, parent, attrs):
        super().__init__(parent,
                         title="Attributes",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self.infoList = InfoListCtrl(self)
        self.search = AutocompleteTextCtrl(self)
        self.search.SetHint('searching ...')
        self.attrs = attrs
        data = {'key': list(attrs.keys()), 'value': list(attrs.values())}
        self.infoList.Load(pd.DataFrame.from_records(data))
        szAll = wx.BoxSizer(wx.VERTICAL)
        szAll.Add(self.search, 0, wx.EXPAND | wx.ALL, 0)
        szAll.Add(self.infoList, 1, wx.EXPAND | wx.ALL, 0)

        self.SetSizer(szAll)
        self.Layout()
        szAll.Fit(self)

        self.Bind(wx.EVT_TEXT, self.OnDoSearch, self.search)

    def OnDoSearch(self, evt):
        pattern = self.search.GetValue()
        self.infoList.Fill(pattern)

class NCTree(TreeCtrlNoTimeStamp):
    ID_SHOW_ATTRIBUTES = wx.NewIdRef()

    def __init__(self, parent, style=wx.TR_DEFAULT_STYLE):
        super().__init__(parent, style)
        self.attrs = {}

    def GetItemDataFromPath(self, path):
        d = super().GetItemDataFromPath(path)
        if not self._is_folder(d):
            d = np.array(d)
        return d

    def get_children(self, item):
        children = super().get_children(item)
        children = [c for c in children if c['label'] != 'ncattrs']
        return children

    def Load(self, data, filename=None):
        # data: [data, attrs]
        self.attrs = data[1]
        super().Load(data[0], filename)

    def GetItemAttrs(self, item):
        if item == self.GetRootItem():
            return []

        path = self.GetItemPath(item)
        attrs = self.GetItemAttrsFromPath(path)
        if self.ItemHasChildren(item):
            return attrs.get('.', [])
        return attrs

    def GetItemAttrsFromPath(self, path):
        # path is an array, e.g., path = get_tree_item_path(name)
        d = self.attrs
        for i, p in enumerate(path):
            if p not in d:
                if isinstance(d, pd.DataFrame):
                    # the name in node DataFrame is not parsed, so try the
                    # combined name, e.g., if the column name is a[5],
                    # get_tree_item_path will return ['a', '[5]']
                    name = get_tree_item_name(path[i:])
                    if name in d:
                        return d[name]
                return None
            d = d[p]
        return d

    def GetItemMenu(self, item):
        menu = super().GetItemMenu(item)
        if menu is None:
            return None
        data = self.GetItemAttrs(item)
        if data:
            menu.Insert(0, self.ID_SHOW_ATTRIBUTES, "Show attributes")
            menu.InsertSeparator(1)
        return menu

    def doProcessCommand(self, cmd, item):
        if cmd == self.ID_SHOW_ATTRIBUTES:
            attr = self.GetItemAttrs(item)
            dlg = AttrsDialog(self, attr)
            dlg.ShowModal()
        else:
            super().doProcessCommand(cmd, item)

class NCPanel(PanelNotebookBase):
    Gcc = Gcm()

    def __init__(self, parent, filename=None):
        PanelNotebookBase.__init__(self, parent, filename=filename)

        self.Bind(wx.EVT_TEXT, self.OnDoSearch, self.search)

    def init_pages(self):
        # data page
        panel, self.search, self.tree = self.CreatePageWithSearch(NCTree)
        self.notebook.AddPage(panel, 'Data')

        # load the nc
        self.nc = None

    def doLoad(self, filename, add_to_history=True, data=None):
        """load the netCDF file"""
        u = data
        if u is None:
            u = self.open(filename)
        self.nc = u
        if u:
            self.tree.Load(u, filename)
        else:
            self.tree.Load(None)
            add_to_history = False

        super().doLoad(filename, add_to_history=add_to_history, data=data)

    def OnDoSearch(self, evt):
        pattern = self.search.GetValue()
        self.tree.Fill(pattern)
        item = self.tree.FindItemFromPath(self.tree.x_path)
        if item:
            self.tree.SetItemBold(item, True)
        self.search.SetFocus()

    @classmethod
    def GetFileType(cls):
        return "netCDF files (*.nc)|*.nc|All files (*.*)|*.*"

    @classmethod
    def do_open(cls, filename):
        return load_nc(filename)

class NC(FileViewBase):
    name = 'netCDF'
    panel_type = NCPanel

    @classmethod
    def check_filename(cls, filename):
        if not super().check_filename(filename):
            return False

        if filename is None:
            return True

        _, ext = os.path.splitext(filename)
        return (ext.lower() in ['.nc'])

    @classmethod
    def initialized(cls):
        # add nc to the shell
        dp.send(signal='shell.run',
                command='from bsmplot.bsm.nc import NC',
                prompt=False,
                verbose=False,
                history=False)

    @classmethod
    def get(cls, num=None, filename=None, data_only=True):
        manager = super().get(num, filename, data_only)
        nc = None
        if manager:
            nc = manager.nc
        elif filename:
            try:
                nc = load_nc(filename)
            except:
                traceback.print_exc(file=sys.stdout)
        return nc

def bsm_initialize(frame, **kwargs):
    NC.initialize(frame)
