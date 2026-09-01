#!/usr/bin/env python3
"""Materialize the current Doge v5 plugin architecture without starting AstrBot.

The historical feature catalog is deliberately not a deployment manifest.
Default profile installs only stable/formal v5 domains plus doge_shared.
Legacy museum is opt-in; planned plugins with no main.py are never installed.
"""
from __future__ import annotations
import argparse,json,shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PLUGINS=ROOT/'plugins'
MANIFEST=ROOT/'plugin_manifest.json'

def units(profile:str,only:set[str]|None):
 data=json.loads(MANIFEST.read_text(encoding='utf-8'))
 names=list(data.get('shared',[]))
 for item in data['plugins']:
  if item.get('status') in {'planned','merged'}: continue
  if profile=='default' and not item.get('default'): continue
  if profile=='legacy' and item.get('status')!='legacy': continue
  names.append(item['name'])
 if only:
  # shared libraries are automatically kept when any real plugin is requested.
  names=[n for n in names if n in only or n in data.get('shared',[])]
 out=[]
 for name in dict.fromkeys(names):
  src=(PLUGINS/name).resolve()
  if not src.exists(): raise FileNotFoundError(src)
  if name not in data.get('shared',[]) and not (src/'main.py').exists():
   raise RuntimeError(f'plugin has no main.py: {name}')
  out.append((name,src))
 return out

def main():
 p=argparse.ArgumentParser(); p.add_argument('--dest',required=True,type=Path); p.add_argument('--mode',choices=['symlink','copy'],default='symlink'); p.add_argument('--profile',choices=['default','all','legacy'],default='default'); p.add_argument('--only',action='append',default=[]); p.add_argument('--dry-run',action='store_true'); p.add_argument('--force',action='store_true'); a=p.parse_args()
 dest=a.dest.expanduser().resolve(); us=units(a.profile,set(a.only) or None)
 print(f'destination: {dest}\nmode: {a.mode}; profile: {a.profile}; units: {len(us)}')
 for name,src in us:
  target=dest/name; print(f'{name:24} <- {src}')
  if a.dry_run: continue
  dest.mkdir(parents=True,exist_ok=True)
  if target.exists() or target.is_symlink():
   if not a.force: raise FileExistsError(f'{target} exists; use --force only when replacement is intended')
   shutil.rmtree(target) if target.is_dir() and not target.is_symlink() else target.unlink()
  target.symlink_to(src,target_is_directory=True) if a.mode=='symlink' else shutil.copytree(src,target)
 if a.dry_run: print('dry-run: no filesystem changes made')

if __name__=='__main__': main()
