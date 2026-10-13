def classFactory(iface):  # noqa: N802 (name required by QGIS)
    from .plugin import Maps4DronePlugin

    return Maps4DronePlugin(iface)
