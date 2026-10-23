#!/usr/bin/env python3
"""Opt-in local vision evaluation using synthetic screens, never desktop capture.

Requires Pillow for generated fixtures. Reports literal recognition checks and
wall time; this is not a broad accuracy score or an end-to-end desktop test.
"""
import argparse
import importlib.util
import io
import json
import re
from pathlib import Path
import time
from PIL import Image, ImageDraw, ImageFont


def fixture(result, state):
    image=Image.new('RGB',(800,450),'#20242b')
    draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',32)
    large=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',72)
    draw.text((35,25),'Calculator — test fixture',font=font,fill='white')
    draw.rectangle((30,110,770,260),fill='#343a44')
    draw.text((80,135),result,font=large,fill='white')
    draw.text((35,330),'Automation: '+state,font=font,fill='white')
    output=io.BytesIO();image.save(output,format='PNG');return output.getvalue()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',default='desktop-observer-local')
    parser.add_argument('--api',default='http://127.0.0.1:1234')
    args=parser.parse_args()
    source=Path(__file__).resolve().parents[1]/'examples/notification_observer.py'
    spec=importlib.util.spec_from_file_location('observer_benchmark_client',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    model=module.LocalModel(args.api,args.model)
    passed=True
    for result,state in [('135','paused'),('42','active'),('126','paused'),('15','active')]:
        started=time.monotonic()
        try:
            description=model.describe(fixture(result,state))
            checks={'result_recognized':bool(re.search(r'\b'+re.escape(result)+r'\b',description)),
                    'state_recognized':bool(re.search(r'\b'+state+r'\b',description.lower())),
                    'app_recognized':'calculator' in description.lower()}
            passed=passed and all(checks.values())
            print(json.dumps({'fixture':state,'expected_result':result,'seconds':round(time.monotonic()-started,2),
                              'checks':checks,'description':description}),flush=True)
        except Exception as error:
            passed=False
            print(json.dumps({'fixture':state,'expected_result':result,'seconds':round(time.monotonic()-started,2),
                              'error_kind':type(error).__name__}),flush=True)

    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
