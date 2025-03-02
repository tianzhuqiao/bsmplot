# bsmplot
**bsmplot** is a cross-platform tool to visualize time series based on [Matplotlib](https://matplotlib.org/) and [wxPython](https://wxpython.org/).

<img src="https://github.com/tianzhuqiao/bsmplot/blob/main/docs/bsmplot.png?raw=true" width="865"></img>

## Installation
```
$ pip install bsmplot
```

To start from terminal
```
$ bsmplot
```

Add shortcut to desktop / Start Menu
```
$ bsmplot --init
```

##  Supported data source
- VCD (value change dump)
- PX4 [ulog](https://docs.px4.io/main/en/dev_log/ulog_file_format.html)
- CSV
- Matlab (.mat)
- [HDF5](https://docs.h5py.org/en/stable/)
- [netCDF](https://unidata.github.io/netcdf4-python/)
- [ZMQ](https://zeromq.org/) subscriber. **json** format is supported by defaut. If corresponding package is installed, the following format is also supported
    - [bson](https://github.com/py-bson/bson)
    - [cbor](https://github.com/agronholm/cbor2)
    - [msgpack](https://msgpack.org/)

## Plot the data
To plot the data, simply double click a signal. It will plot the signal on the current figure window (or create one if there is no figure window then plot).

<img src="https://github.com/tianzhuqiao/bsmplot/blob/main/docs/plot.png?raw=true" width="600"></img>

You can also drag the signal to the figure window.

If the data has timestamp field (e.g., ulog), it will be used as x-axis data; otherwise (e.g., csv), the x-axis will be the index by default. And you can also set some signal as x-axis data, which will be shown in **bold**.

<img src="https://github.com/tianzhuqiao/bsmplot/blob/main/docs/plot3.png?raw=true" width="600"></img>

Many operations of the figure can be done via the context menu (right click), and the toolbar on top. For example, to create a subplot with shared x-axis,

<img src="https://github.com/tianzhuqiao/bsmplot/blob/main/docs/plot2.png?raw=true" width="600"></img>

If the signal has 2d/3d data, it will be shown in [glsurface](https://github.com/tianzhuqiao/glsurface) window. For 3d data, the 1st dimension will be treated as time axis.
<img src="https://github.com/tianzhuqiao/bsmplot/blob/main/docs/glsurface.png?raw=true" width="600"></img>

## Process the data

To process the data, right click the signal, and select the function to run. Following functions are pre-defined

1. Quaternion to Yaw/Pitch/Roll
2. Radian to degree
3. Degree to Radian
4. Moving average

<img src="https://github.com/tianzhuqiao/bsmplot/blob/main/docs/quat2angle.png?raw=true" width="600"></img>

If you are familiar with python code, you can add your own functions. You basically need to define the **inputs**, **equation**, and **outputs**. The number of **outputs** must match the actual ones returned from the **equation**.

<img src="https://github.com/tianzhuqiao/bsmplot/blob/main/docs/addfunc.png?raw=true" width="400"></img>

If the processing is too complicated, you can also export the data to shell: right click -> Export to shell (or Export to shell with timestamp if available)

<img src="https://github.com/tianzhuqiao/bsmplot/blob/main/docs/exportdata.png?raw=true" width="600"></img>

Then in the shell, you can access the exported data, and run any python command.

<img src="https://github.com/tianzhuqiao/bsmplot/blob/main/docs/exportdata2.png?raw=true" width="600"></img>
