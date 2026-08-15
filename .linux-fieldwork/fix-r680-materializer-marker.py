from pathlib import Path

path = Path('.linux-fieldwork/materialize-r680.py')
text = path.read_text()
old = 'marker = "/// This trait defines a set of functions which can be triggered whenever a PCI device is modified in any way.\\n"'
new = 'marker = "/// This trait defines a set of functions which can be triggered whenever a\\n/// PCI device is modified in any way.\\n"'
if old not in text:
    raise SystemExit('old DeviceRelocation materializer marker missing')
path.write_text(text.replace(old, new, 1))
