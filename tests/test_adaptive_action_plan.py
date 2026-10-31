"""Work order responds to failures and cannot confuse passing tests with the goal."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from action_plan import choose, snapshot, source_hashes, REGISTRY, REGRESSION, LIVE
from feedback_journal import append


class Plan(unittest.TestCase):
    def test_new_failures_reopen_prior_work_and_structural_failures_block_publication(self):
        healthy = {"regression_fresh_pass": True, "live_fresh_pass": True}
        self.assertEqual(choose(healthy)["id"], "STRUCTURE_CAUSAL")
        self.assertEqual(choose(dict(healthy, training_run_failed=True))["id"], "REPAIR_TRAINING")
        self.assertEqual(choose(dict(healthy, relational_foundation_fresh_pass=True))["id"], "STRUCTURE_RULE_LEARNING")
        self.assertEqual(choose(dict(healthy, relational_foundation_fresh_pass=True,
                                     organisation_rule_execution_fresh_pass=True))["id"], "SELF_ACTION_OUTCOME")
        self.assertEqual(choose(dict(healthy, relational_foundation_fresh_pass=True,
                                     organisation_rule_execution_fresh_pass=True,
                                     self_action_revision_fresh_pass=True))["id"], "SELF_GOAL_ORGANISATION")
        self.assertEqual(choose(dict(healthy, relational_foundation_fresh_pass=True,
                                     organisation_rule_execution_fresh_pass=True,
                                     self_action_revision_fresh_pass=True,
                                     declared_goal_process_fresh_pass=True))["id"], "GOAL_RULE_INTEGRATION")
        self.assertEqual(choose(dict(healthy, relational_foundation_fresh_pass=True,
                                     unresolved_content_failures=["x"]))["id"], "REPAIR_CONTENT")
        self.assertEqual(choose(dict(healthy, unresolved_content_failures=["x"]))["id"], "REPAIR_CONTENT")
        self.assertEqual(choose(dict(healthy, structure_counterevidence=["x"]))["id"], "REFUTE_STRUCTURE")
        self.assertEqual(choose(dict(healthy, regression_fresh_pass=False))["id"], "REPAIR_BASELINE")
        self.assertEqual(choose(dict(healthy, live_fresh_pass=False))["id"], "LIVE_DIAGNOSIS")

    def test_old_pass_does_not_certify_changed_code_and_ratings_do_not_certify_development(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "spec").mkdir()
            (root / "engine").mkdir()
            (root / REGISTRY).write_text(json.dumps({"schema": 1, "objective": "像人一样",
                                                    "issues": [{"id": "memory", "engineering_repair": True}]}))
            source = root / "engine/demo.py"
            source.write_text("v1")
            hashes = source_hashes(root)
            (root / REGRESSION).write_text(json.dumps({"all_checks_passed": True, "source_hashes": hashes}))
            (root / LIVE).write_text(json.dumps({"passed": True, "source_hashes": hashes,
                                                "joint_development_verified": True}))
            result = snapshot(root)
            self.assertEqual(result["next_action"]["id"], "STRUCTURE_CAUSAL")
            self.assertFalse(result["goal_achieved"])
            self.assertEqual(result["development_credit"], 0)
            (root / "state/train").mkdir(parents=True)
            progress = root / "state/train/progress.json"
            progress.write_text(json.dumps({"run_id": "failed", "failure": "tutor_generation_failed", "turns_added": 0}))
            self.assertEqual(snapshot(root)["next_action"]["id"], "REPAIR_TRAINING")
            progress.write_text(json.dumps({"run_id": "recovered", "failure": None, "turns_added": 6}))
            self.assertEqual(snapshot(root)["next_action"]["id"], "STRUCTURE_CAUSAL")
            source.write_text("v2")
            self.assertEqual(snapshot(root)["next_action"]["id"], "REPAIR_BASELINE")

    def test_bounded_execution_adapter_requires_current_causal_checks_but_never_stage_credit(self):
        from action_plan import FOUNDATION, ORGANISATION, SELF_ACTION, SELF_GOAL, SELF_GOAL_LIVE
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'spec').mkdir()
            (root/REGISTRY).write_text(json.dumps({'schema':1,'objective':'像人一样','issues':[]}))
            hashes=source_hashes(root)
            for name,key in [(REGRESSION,'all_checks_passed'),(LIVE,'passed')]:
                (root/name).write_text(json.dumps({key:True,'source_hashes':hashes}))
            (root/FOUNDATION).write_text(json.dumps({'schema':1,'passed':True,'source_hashes':hashes,
                'rule_origin':'engineered','learned_rule_change':False,
                'cases':[{'passed':True,'ablation_loses_selected_relation':True,'unaffected_object_retained':True,'restart_equal':True}]*3}))
            proof={'schema':1,'passed':True,'source_hashes':hashes,'scope':'bounded_linguistic_rule_execution',
                   'feedback_origin':'declared_engineered_fixture','causal_pipeline_contrast':True,
                   'restart_equal':True,'same_turn_withdrawal':True,'old_context_retained':True,
                   'formation_validation_disjoint':True,'development_credit':0}
            path=root/ORGANISATION;path.write_text(json.dumps(proof))
            current=snapshot(root)
            self.assertEqual(current['next_action']['id'],'SELF_ACTION_OUTCOME')
            self.assertFalse(current['signals']['causal_organisation_verified'])
            self.assertFalse(current['goal_achieved'])
            own={'schema':1,'passed':True,'source_hashes':hashes,'scope':'bounded_own_response_revision',
                 'goal_origin':'engineered_dialogue_obligation','real_API':False,'development_credit':0,
                 'cases':[{'case':name,'passed':True} for name in (
                     'identical_history_enable_disable','restart_resumes_committed_failure',
                     'permission_not_semantic_fulfillment','fresh_second_review_can_reconsider','changed_evidence_reopens')]}
            (root/SELF_ACTION).write_text(json.dumps(own))
            goal={'schema':1,'passed':True,'source_hashes':hashes,'scope':'source_bound_declared_goal_commitments',
                  'goal_origin':'model_declared_bounded_task','selection_origin':'declared_engineered_selection_and_review',
                  'real_API':False,'development_credit':0,'cases':[{'case':name,'passed':True} for name in (
                      'identical_history_goal_ablation','paraphrase_resume','source_change_reconsider',
                      'conflict_complete_quotes','decline_retires_pending','literal_outcome_not_semantic_fit','other_object_preserved')]}
            (root/SELF_GOAL).write_text(json.dumps(goal))
            self.assertEqual(snapshot(root)['next_action']['id'],'SELF_GOAL_ORGANISATION')
            actual={'passed':True,'source_hashes':hashes,'real_API':True,'goal_origin':'model_declared_bounded_task',
                    'cases':[{'case':name,'passed':True} for name in ('actual_relation_seed',
                        'actual_choice_with_injected_candidate_failure','actual_paraphrase_resume',
                        'actual_source_change_reconsider','actual_conflict_quotes_complete')]}
            (root/SELF_GOAL_LIVE).write_text(json.dumps(actual))
            self.assertEqual(snapshot(root)['next_action']['id'],'GOAL_RULE_INTEGRATION')
            self.assertFalse(snapshot(root)['signals']['causal_organisation_verified'])
            (root/SELF_GOAL_LIVE).write_text(json.dumps(dict(actual,source_hashes={})))
            self.assertEqual(snapshot(root)['next_action']['id'],'SELF_GOAL_ORGANISATION')
            (root/SELF_GOAL_LIVE).write_text(json.dumps(actual))
            self.assertEqual(snapshot(root)['next_action']['id'],'GOAL_RULE_INTEGRATION')
            (root/SELF_ACTION).write_text(json.dumps(dict(own,goal_origin='autonomous_subjective_desire')))
            self.assertEqual(snapshot(root)['next_action']['id'],'SELF_ACTION_OUTCOME')
            (root/SELF_ACTION).write_text(json.dumps(own))
            for key in ['causal_pipeline_contrast','same_turn_withdrawal','formation_validation_disjoint']:
                path.write_text(json.dumps(dict(proof,**{key:False})))
                self.assertEqual(snapshot(root)['next_action']['id'],'STRUCTURE_RULE_LEARNING')

    def test_external_feedback_is_not_autobiography_or_psychological_credit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feedback.jsonl"
            evidence = {"verdict": "UNKNOWN", "independent_semantic_review_verified": False}
            event_id = append(path, raw="输入", origin={"kind": "test"}, turn=1,
                              attempts=[{"content_review": evidence}], final_accepted=False)
            row = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(row["event_id"], event_id)
            self.assertEqual(row["development_credit"], 0)
            self.assertFalse(row["final_accepted"])
            self.assertEqual(row["kind"], "content_review_opinion")


if __name__ == "__main__":
    unittest.main()
