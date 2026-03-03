import sys
import os
import app.api.webhooks

import inspect

print(f"Python executable: {sys.executable}")
print(f"CWD: {os.getcwd()}")
try:
    print(f"app.api.webhooks file: {app.api.webhooks.__file__}")
    source = inspect.getsource(app.api.webhooks.whatsapp_webhook)
    if "demo" in source:
        print("FOUND: 'demo' string in source")
    else:
        print("MISSING: 'demo' string in source")
        
    if "CUSTOM ERROR" in source:
        print("FOUND: 'CUSTOM ERROR' string in source")
    else:
        print("MISSING: 'CUSTOM ERROR' string in source")
        
except Exception as e:
    print(f"Error getting source: {e}")
print(f"sys.path: {sys.path}")
