"""Rule execution, atomic withdrawal and causal intervention in real Pipeline.

All labels below are declared engineered fixtures, never independent human
feedback. No real state or network is used and no stage credit is awarded.
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engine"))
from relation_learning import RelationLearning
from pipeline import Pipeline
from organisation_runtime import select
from tests.test_relation_pipeline import Reviewer
from tools.structure_scope_trial import state_hashes


def text(quoted, suffix):
    return ('他写下“不要说”，我认定' if quoted else '不要说，这种话：') + '都是他们害了' + suffix + '。'


def intake(learner, quoted, suffix, role=None):
    raw = text(quoted, suffix)
    start = raw.index('都是他们')
    return learner.observe(raw, start, start + 4, 'blame_external', {'blame_external'},
                           role or ('ASSERTED' if quoted else 'PROHIBITED'),
                           source='offline_fixture' if learner.offline else 'external_reviewer',
                           observer='declared_engineered_fixture', turn=1)


def form(learner, validate=True):
    for i in range(5):
        intake(learner, False, '原项目%d' % i)
    for i in range(3):
        intake(learner, True, '新合同%d' % i)
    if validate:
        for quoted in (False, True):
            for i in range(2):
                intake(learner, quoted, '后来比赛%d' % i)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.before = state_hashes()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'relation_rules.json'
        self.learner = RelationLearning(self.path, offline=True)

    def tearDown(self):
        self.tmp.cleanup()
        self.assertEqual(self.before, state_hashes())

    def predict(self, learner, quoted, suffix='未见任务'):
        raw = text(quoted, suffix); start = raw.index('都是他们')
        return learner.predict(raw, start, start + 4, 'blame_external', {'blame_external'})

    def test_form_later_activate_restart_and_effect_of_removing_rule(self):
        form(self.learner, validate=False)
        runtime = self.learner.learner.data['organisation_runtime']
        self.assertEqual(runtime['versions'][0]['status'], 'candidate')
        self.assertFalse(self.predict(self.learner, False).get('execution'))
        proof = copy.deepcopy(runtime['versions'][0]['proof'])
        for quoted in (False, True):
            for i in range(2):
                intake(self.learner, quoted, '后来比赛%d' % i)
        version = runtime['versions'][0]
        self.assertEqual(version['status'], 'active')
        self.assertEqual(version['proof'], proof)
        resumed = RelationLearning(self.path, offline=True)
        left, right = self.predict(resumed, False), self.predict(resumed, True)
        self.assertEqual((left['role'], right['role']), ('PROHIBITED', 'ASSERTED'))
        self.assertEqual(left['execution']['operation'], 'RESOLVE_PROPOSITION_ROLE')
        without = RelationLearning(self.path, offline=True, use_organisation=False)
        self.assertNotEqual(self.predict(without, False)['role'], left['role'])
        self.assertFalse(self.predict(without, False).get('execution'))
        self.assertEqual(runtime['development_credit'], 0)

    def test_current_counterexample_withdraws_before_current_prediction_and_never_revives_alias(self):
        form(self.learner)
        before = copy.deepcopy(self.learner.learner.data['organisation_runtime']['versions'][0]['proof'])
        result = intake(self.learner, True, '后来的反例', role='NEGATED')
        self.assertFalse(result['feedback']['observed_role_agreement'])
        self.assertEqual(result['feedback']['organisation_operation']['result'], 'ASSERTED')
        version = self.learner.learner.data['organisation_runtime']['versions'][0]
        self.assertEqual(version['status'], 'withdrawn')
        self.assertEqual(version['proof'], before)
        self.assertEqual(self.predict(self.learner, False)['role'], 'UNKNOWN')
        for i in range(5):
            intake(self.learner, False, '重新确认%d' % i)
        self.assertEqual(self.predict(self.learner, False)['role'], 'UNKNOWN')
        self.assertEqual(self.learner.learner.data['organisation_runtime']['versions'][0]['status'], 'withdrawn')

    def test_other_covered_context_refutes_whole_rule_and_current_other_slots_are_not_resurrected(self):
        for i in range(5):
            raw = '不能说，都是他们害了背景%d。' % i; start = raw.index('都是他们')
            self.learner.observe(raw, start, start + 4, 'blame_external', {'blame_external'},
                                 'NEGATED', source='offline_fixture', observer='fixture', turn=1)
        form(self.learner)
        raw = '不能说，都是他们害了背景反例。'; start = raw.index('都是他们')
        self.learner.observe(raw, start, start + 4, 'blame_external', {'blame_external'},
                             'ASSERTED', source='offline_fixture', observer='fixture', turn=1)
        self.assertEqual(self.predict(self.learner, False)['role'], 'UNKNOWN')
        self.assertEqual(self.learner.learner.data['organisation_runtime']['versions'][0]['status'], 'withdrawn')
        self.assertEqual(self.learner.predict(raw, start, start + 4, 'blame_external', {'blame_external'})['role'], 'UNKNOWN')

    def test_forged_activation_altered_program_missing_evidence_and_old_snapshot_cannot_execute(self):
        form(self.learner, validate=False)
        data = self.learner.learner.data
        data['organisation_runtime']['versions'][0]['status'] = 'active'
        data['organisation_runtime']['versions'][0]['activated_at'] = 8
        self.assertEqual(self.predict(self.learner, False)['role'], 'UNKNOWN')
        data['organisation_runtime']['versions'][0]['proof']['program']['branches']['False'] = 'ASSERTED'
        with self.assertRaises(ValueError):
            self.predict(self.learner, False)
        # Historical candidates lacking a committed executable version stay old.
        self.learner = RelationLearning(Path(self.tmp.name) / 'fresh.json', offline=True)
        form(self.learner)
        old = copy.deepcopy(self.learner.learner.data); old.pop('organisation_runtime')
        raw = text(False, '历史快照'); start = raw.index('都是他们')
        self.assertIsNone(select(old, self.learner.context(raw, start, start+4, 'blame_external', {'blame_external'}), raw, start, start+4))
        self.learner.learner.data['structure_evidence']['cases'] = []
        self.assertEqual(self.predict(self.learner, False)['role'], 'UNKNOWN')

    def test_failed_atomic_activation_restores_rule_evidence_and_runtime_together(self):
        form(self.learner, validate=False)
        for quoted, suffix in [(False,'后来甲'),(False,'后来乙'),(True,'后来甲')]:
            intake(self.learner, quoted, suffix)
        before = copy.deepcopy(self.learner.learner.data); disk = self.path.read_bytes()
        with patch('relation_learning.atomic_json', side_effect=OSError('fixture atomic failure')):
            with self.assertRaises(OSError):
                intake(self.learner, True, '后来乙')
        self.assertEqual(self.learner.learner.data, before)
        self.assertEqual(self.path.read_bytes(), disk)
        self.assertEqual(before['organisation_runtime']['versions'][0]['status'], 'candidate')

    def test_later_source_hash_and_ownership_are_checked_before_execution(self):
        form(self.learner)
        data=self.learner.learner.data
        data['structure_evidence']['cases'][-1]['raw_text']='原文被替换'
        self.assertEqual(self.predict(self.learner,False)['role'],'UNKNOWN')
        self.learner = RelationLearning(Path(self.tmp.name)/'untraced.json',offline=True)
        form(self.learner,validate=False)
        # Old candidate observations are insufficient to publish without text.
        for case in self.learner.learner.data['structure_evidence']['cases']:
            case.pop('raw_text',None)
        for quoted in (False,True):
            for i in range(2):intake(self.learner,quoted,'新来源%d'%i)
        versions=self.learner.learner.data['organisation_runtime']['versions']
        self.assertFalse(any(v['status']=='active' for v in versions))

    def test_visibility_unknown_quotes_and_offline_scope_remain_boundaries(self):
        form(self.learner)
        raw = text(False,'关门'); start=raw.index('都是他们')
        self.assertEqual(self.learner.predict(raw,start,start+4,'blame_external',set())['role'],'UNKNOWN')
        production = RelationLearning(self.path, offline=False)
        self.assertFalse(self.predict(production,False).get('execution'))
        self.assertEqual(self.predict(production,False)['role'],'UNKNOWN')
        # Same old literal features, but unsupported ownership is abstention.
        raw='他写下「不要说」，都是他们害了合同。';start=raw.index('都是他们')
        result=self.learner.predict(raw,start,start+4,'blame_external',{'blame_external'})
        self.assertEqual(result['role'],'UNKNOWN')

    def test_live_pipeline_contrast_trace_restart_and_same_turn_withdrawal(self):
        directory = Path(self.tmp.name) / 'pipeline'
        def pipe(enabled=True):
            return Pipeline(ledger_path=str(directory/'state/ledger.jsonl'),
                            character_path=str(directory/'state/character.json'),
                            devlevel_path=str(directory/'state/devlevel_verified.json'),
                            carry_root=str(directory), gate_perception=True, use_organisation_rules=enabled,
                            use_api=False,use_render=False,use_think=False,auto_audit=False)
        p=pipe()
        for quoted,count,label in [(False,5,'原'),(True,3,'形成'),(False,2,'验证'),(True,2,'验证')]:
            p.reader=Reviewer('ASSERTED' if quoted else 'PROHIBITED')
            for i in range(count):p.turn(text(quoted,label+str(i)))
        frozen=(directory/'state/relation_rules.json').read_bytes()
        p=pipe();p.reader=None
        after=p.turn(text(False,'从未出现的对象'))
        disabled=pipe(False);disabled.reader=None
        before=disabled.turn(text(False,'另一未见对象'))
        self.assertNotIn('blame_external',after.markers)
        self.assertIn('blame_external',before.markers)
        trace=json.loads(next(n for n in after.notes if n.startswith('关系学习=')).split('=',1)[1])
        self.assertEqual(trace['occurrences'][0]['after_execution']['result'],'PROHIBITED')
        self.assertEqual((directory/'state/relation_rules.json').read_bytes(),frozen)
        p.reader=Reviewer('NEGATED')
        current=p.turn(text(True,'当轮反例'))
        trace=json.loads(next(n for n in current.notes if n.startswith('关系学习=')).split('=',1)[1])
        self.assertEqual(trace['occurrences'][0]['before'],'ASSERTED')
        self.assertEqual(trace['occurrences'][0]['after'],'UNKNOWN')
        self.assertFalse(trace['suppressed'])
        dev=json.loads((directory/'state/devlevel_verified.json').read_text(encoding='utf-8'))
        self.assertEqual((dev['level'],dev['equilibration']),('I-3',0))


if __name__ == '__main__':
    unittest.main()
