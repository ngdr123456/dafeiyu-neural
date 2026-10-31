"""Disposable Pipeline contrast for bounded rule execution, with declared labels.

--api also asks the actual structured reader about the formation/validation
inputs. Those model annotations remain opinions and may fail this diagnostic.
"""
import argparse
import copy
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'engine'))
from action_plan import ORGANISATION, source_hashes
from pipeline import Pipeline
from understand import ApiReader
from input_provenance import digest
from tests.test_relation_pipeline import Reviewer
from tests.test_organisation_runtime import text
from tools.structure_scope_trial import state_hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api',action='store_true')
    parser.add_argument('--report',default=ORGANISATION)
    args=parser.parse_args()
    before=state_hashes(); initial=source_hashes(ROOT)
    result={'schema':1,'scope':'bounded_linguistic_rule_execution',
            'feedback_origin':'actual_model_annotation' if args.api else 'declared_engineered_fixture',
            'scripted_inputs':True,'real_API':args.api,'independent_semantics_verified':False,
            'development_credit':0,'cases':[],'source_hashes':initial}
    with tempfile.TemporaryDirectory(prefix='ego-organisation-execution-') as tmp:
        directory=Path(tmp)
        def pipe(enabled=True):
            return Pipeline(ledger_path=str(directory/'state/ledger.jsonl'),
                            character_path=str(directory/'state/character.json'),
                            devlevel_path=str(directory/'state/devlevel_verified.json'),
                            carry_root=str(directory),gate_perception=True,use_organisation_rules=enabled,
                            use_api=False,use_think=False,use_render=False,auto_audit=False)
        p=pipe()
        def origin(raw,kind='scripted_diagnostic'):
            return {'schema':1,'kind':kind,'input_sha256':digest(raw),'topic_id':None,
                    'independent_human_input_verified':False}
        reader=ApiReader() if args.api else None
        ready=not args.api or reader.available
        if not ready:result['cases'].append({'case':'api_available','passed':False})
        # Extra context tests continuity: the new split must not resurrect or
        # replace this separately learned, presently valid relation.
        samples=[('不能说，都是他们害了背景%d。'%i,'NEGATED') for i in range(5)] if not args.api else []
        samples += [(text(quoted,label+str(i)),'ASSERTED' if quoted else 'PROHIBITED')
                    for quoted,count,label in [(False,5,'原项目'),(True,3,'形成合同'),(False,2,'后来比赛'),(True,2,'后来比赛')]
                    for i in range(count)]
        for index,(raw,expected) in enumerate(samples,1):
            if not ready:break
            if args.api:
                reading=reader.read(raw,'',p.markers.rules['markers'])
                start=raw.index('都是他们')
                annotations=[x for x in reading.relations if x['id']=='blame_external']
                required={(m.start(),m.end()) for phrase in p.relation_learning.rules['blame_external']['patterns']
                          for m in re.finditer(re.escape(phrase),raw)}
                observed={(x['start'],x['end']) for x in annotations}
                label=[x['role'] for x in annotations]
                passed=reading.ok and observed==required and all(x['role']==expected for x in annotations)
                result['cases'].append({'case':'actual_annotation:%d'%index,'passed':bool(passed),
                    'input':raw,'expected_engineered_role':expected,'model_role':label,
                    'reader_ok':reading.ok,'dropped':reading.dropped,'error':reading.error})
                print(result['cases'][-1]['case'],passed,label,flush=True)
                if not passed:ready=False;break
                for item in annotations:
                    p.relation_learning.observe(raw,item['start'],item['end'],'blame_external',{'blame_external'},item['role'],
                        source='external_reviewer',observer='api_reader:'+reader.model,turn=index,input_origin=origin(raw))
            else:
                p.reader=Reviewer(expected)
                p.turn(raw,input_origin=origin(raw))
        data=p.relation_learning.learner.data
        runtime=copy.deepcopy(data.get('organisation_runtime',{}))
        probe=text(False,'完全未见的工作');start=probe.index('都是他们')
        guard=p.relation_learning.context(probe,start,start+4,'blame_external',{'blame_external'})
        active=[v for v in runtime.get('versions',[]) if v['status']=='active' and v['proof']['program']['guard']==guard]
        ready=ready and len(active)==1
        result['cases'].append({'case':'formation_then_later_activation','passed':ready,'runtime':runtime})
        result.update(causal_pipeline_contrast=False,restart_equal=False,same_turn_withdrawal=False,
                      old_context_retained=False,formation_validation_disjoint=False)
        if ready:
            rule=active[0]; proof=rule['proof']
            from organisation_refinement import derive
            candidate=next(c for c in derive(data['structure_evidence']) if c['sid']==rule['sid'])
            validation=set(sum(candidate['validation_inputs'].values(),[]))
            result['formation_validation_disjoint']=set(proof['formation_inputs']).isdisjoint(validation)
            def prediction(learner,raw):
                start=raw.index('都是他们')
                return learner.predict(raw,start,start+4,'blame_external',{'blame_external'})
            expected=prediction(p.relation_learning,probe)
            disk=(directory/'state/relation_rules.json').read_bytes()
            resumed=pipe(); resumed.reader=None
            restarted=prediction(resumed.relation_learning,probe)
            result['restart_equal']=restarted==expected
            on=resumed.turn(probe,input_origin=origin(probe))
            disabled=pipe(False); disabled.reader=None
            off=disabled.turn(probe,input_origin=origin(probe))
            result['causal_pipeline_contrast']='blame_external' not in on.markers and 'blame_external' in off.markers
            result['cases'].append({'case':'same_input_rule_intervention','passed':result['causal_pipeline_contrast'],
                'input':probe,'enabled_markers':on.markers,'disabled_markers':off.markers,
                'enabled_prediction':restarted,'disabled_prediction':prediction(disabled.relation_learning,probe)})
            assert (directory/'state/relation_rules.json').read_bytes()==disk
            # In actual-model mode continuity is the prior prohibition branch;
            # fixture mode additionally retains another context from the old map.
            retained=prediction(resumed.relation_learning,'不能说，都是他们害了另一背景。') if not args.api else restarted
            result['old_context_retained']=retained['role']==('PROHIBITED' if args.api else 'NEGATED')
            # Deliberate refutation exercises failure handling, not a claim that
            # this sentence really has a NEGATED role. Never conceal that source.
            resumed.reader=Reviewer('NEGATED')
            refutation=text(True,'故意反标签检查')
            challenged=resumed.turn(refutation,input_origin=origin(refutation,'scripted_refutation_fixture'))
            trace=json.loads(next(n for n in challenged.notes if n.startswith('关系学习=')).split('=',1)[1])
            latest=next(v for v in resumed.relation_learning.learner.data['organisation_runtime']['versions']
                        if v['version']==rule['version'])
            result['same_turn_withdrawal']=(latest['status']=='withdrawn' and trace['occurrences'][0]['before']=='ASSERTED'
                                           and trace['occurrences'][0]['after']=='UNKNOWN' and not trace['suppressed'])
            result['cases'].append({'case':'declared_fixture_refutation','passed':result['same_turn_withdrawal'],
                                   'feedback_origin':'declared_engineered_fixture','trace':trace,'withdrawn':latest})
        result['passed']=bool(ready and all(result[k] for k in ['causal_pipeline_contrast','restart_equal',
            'same_turn_withdrawal','old_context_retained','formation_validation_disjoint']))
    if before!=state_hashes() or initial!=source_hashes(ROOT):
        raise RuntimeError('Real state or source changed during isolated trial')
    result['real_state_files_unchanged']=len(before)
    (ROOT/args.report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['passed','real_API','causal_pipeline_contrast','restart_equal','same_turn_withdrawal',
        'old_context_retained','formation_validation_disjoint','real_state_files_unchanged']},ensure_ascii=False))
    return int(not result['passed'])


if __name__=='__main__':
    raise SystemExit(main())
