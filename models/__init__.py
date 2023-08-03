from . import routeros, dellos10, delln

MODELS = {
    "routeros": routeros.RouterOS,
    "dellos10": dellos10.OS10,
    "delln": delln.DellN,
}