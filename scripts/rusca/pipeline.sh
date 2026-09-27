#!/bin/bash
# Full resumable pipeline (all steps cache/skip finished work). Usage: nohup bash scripts/rusca/pipeline.sh > .cache/rusca/pipeline.log 2>&1 &
cd "$(dirname "$0")/../.."
L=.cache/rusca
echo "$(date +%T) translate ru-"; python3 scripts/rusca/translate.py ru- >> $L/pipe-translate.log 2>&1
echo "$(date +%T) translate ca-"; python3 scripts/rusca/translate.py ca- >> $L/pipe-translate.log 2>&1
echo "$(date +%T) translate kvant"; python3 scripts/rusca/translate.py kvant >> $L/pipe-translate.log 2>&1
echo "$(date +%T) kvant ocr"; python3 scripts/rusca/kvant_ocr.py >> $L/pipe-ocr.log 2>&1
python3 scripts/rusca/kvant_raw.py
echo "$(date +%T) kvant junior"; python3 scripts/rusca/kvant_junior.py >> $L/pipe-junior.log 2>&1
echo "$(date +%T) translate kvant (2)"; python3 scripts/rusca/translate.py kvant >> $L/pipe-translate.log 2>&1
echo "$(date +%T) crux extract"; python3 scripts/rusca/pdf_extract.py crux >> $L/pipe-extract.log 2>&1
echo "$(date +%T) translate loop"; bash scripts/rusca/loop.sh
echo "$(date +%T) done"
