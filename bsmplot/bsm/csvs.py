import os
import sys
import traceback
from csv import Sniffer
import wx
import wx.py.dispatcher as dp
import pandas as pd
from bsmutility.pymgr_helpers import Gcm
from bsmutility.utility import build_tree
from bsmutility.fileviewbase import TreeCtrlNoTimeStamp, PanelNotebookBase, FileViewBase

def read_csv(filename):
    try:
        sep = ','
        with open(filename, encoding='utf-8') as fp:
            line = fp.readline()
            s = Sniffer()
            d = s.sniff(line)
            sep = d.delimiter
        csv = pd.read_csv(filename, sep=sep)
        d = {}
        for c in csv:
            d[c] = csv[c]
        return build_tree(build_tree(csv), '->')
    except:
        traceback.print_exc(file=sys.stdout)

class CsvTree(TreeCtrlNoTimeStamp):
    pass


class CsvPanel(PanelNotebookBase):
    Gcc = Gcm()

    def __init__(self, parent, filename=None):
        PanelNotebookBase.__init__(self, parent, filename=filename)

        self.Bind(wx.EVT_TEXT, self.OnDoSearch, self.search)

    def init_pages(self):
        # data page
        panel, self.search, self.tree = self.CreatePageWithSearch(CsvTree)
        self.notebook.AddPage(panel, 'Data')

        # load the csv
        self.csv = None

    def Load(self, filename, add_to_history=True):
        """load the csv file"""
        u = read_csv(filename)
        self.csv = u
        self.tree.Load(u, filename)

        super().Load(filename, add_to_history=add_to_history and u is not None)

    def OnDoSearch(self, evt):
        pattern = self.search.GetValue()
        self.tree.Fill(pattern)
        self.search.SetFocus()

    @classmethod
    def GetFileType(cls):
        return "csv files (*.csv)|*.csv|All files (*.*)|*.*"

class CSV(FileViewBase):
    name = 'csv'
    panel_type = CsvPanel

    @classmethod
    def check_filename(cls, filename):
        if not super().check_filename(filename):
            return False

        if filename is None:
            return True

        _, ext = os.path.splitext(filename)
        return (ext.lower() in ['.csv'])

    @classmethod
    def initialized(cls):
        # add csv to the shell
        dp.send(signal='shell.run',
                command='from bsmplot.bsm.csvs import CSV',
                prompt=False,
                verbose=False,
                history=False)

    @classmethod
    def get(cls, num=None, filename=None, data_only=True):
        manager = super().get(num, filename, data_only)
        csv = None
        if manager:
            csv = manager.csv
        elif filename:
            try:
                csv = read_csv(filename)
            except:
                traceback.print_exc(file=sys.stdout)
        return csv

def bsm_initialize(frame, **kwargs):
    CSV.initialize(frame)
