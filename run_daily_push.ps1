$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python get_data.py
python line_push.py
