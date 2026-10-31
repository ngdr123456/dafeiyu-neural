"""Bounded real API checks for existing memory and new rule execution.

All memories are disposable. Model role annotations are not independent truth;
the deliberate later refutation is explicitly an engineered failure injection.
"""
import json
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'engine'))
from action_plan import LIVE, source_hashes, write_report
from tools.structure_scope_trial import state_hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    if not parser.parse_args().run:
        print('Use --run for the bounded, disposable real API checks; no calls made.')
        return 0
    before=state_hashes();initial=source_hashes(ROOT)
    paths=['spec/组织规则执行模型标注诊断_20261008.json','spec/组织规则执行记忆诊断_20261008.json']
    commands=[['tools/trial_organisation_runtime.py','--api','--report',paths[0]],
              ['tools/verify_goal_live.py','--run','--relations','--report',paths[1]]]
    parts=[];cases=[]
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    for command,path in zip(commands,paths):
        completed=subprocess.run([sys.executable,'-B',*command],cwd=ROOT,env=env,timeout=900)
        report=json.loads((ROOT/path).read_text(encoding='utf-8')) if (ROOT/path).exists() else {}
        valid=completed.returncode==0 and report.get('passed') is True and report.get('source_hashes')==initial
        parts.append({'path':path,'exit_code':completed.returncode,'current_source_passed':valid})
        cases.extend(dict(case,component=path) for case in report.get('cases',[]))
        if not valid:
            cases.append({'case':'component_not_passed:'+path,'passed':False})
            break
    if state_hashes()!=before or source_hashes(ROOT)!=initial:
        raise RuntimeError('Real state or source changed during live verification')
    result={'schema':1,'scope':'scripted_memory_and_model_annotated_bounded_rule_execution',
            'passed':len(parts)==2 and all(p['current_source_passed'] for p in parts),
            'source_hashes':initial,'parts':parts,'cases':cases,'real_API':True,'formal_training':False,
            'scripted_inputs':True,'model_generated_inputs':False,'real_state_files_unchanged':len(before),
            'independent_semantics_verified':False,'development_credit':0,
            'claims':'Listed isolated cases only; engineered operator and model annotations, not human development.'}
    (ROOT/LIVE).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    write_report(ROOT)
    print(json.dumps({'passed':result['passed'],'cases':len(cases),'parts':parts,'state_unchanged':len(before)},ensure_ascii=False))
    return int(not result['passed'])


if __name__=='__main__':
    raise SystemExit(main())
