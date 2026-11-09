"""Manual, code-level offline guard for the bounded experience-intent tests.

This is not an OS sandbox and is not an adversarial-code containment mechanism.
"""
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMP = ROOT / "tests" / "_offline_phase2_continuous_correction_tmp"
RUNTIME = Path(sys.base_prefix).resolve()
TEMP.mkdir(parents=True, exist_ok=True)
os.environ.clear()
os.environ.update({
    "SYSTEMROOT": r"C:\Windows", "WINDIR": r"C:\Windows",
    "TEMP": str(TEMP), "TMP": str(TEMP),
    "USERPROFILE": str(TEMP), "HOME": str(TEMP),
    "BIRTH_MEMORY_PATH": str(TEMP / "synthetic_memory.json"),
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1",
})
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

NODEIDS = [
    "tests/test_birth_body_imagine.py::test_existing_priorities_and_curiosity",
    "tests/test_birth_stance_attitude.py::test_org_and_identity_paths_keep_priority",
    "tests/test_birth_necessary_pain.py::test_hard_priorities",
    "tests/test_birth_phase1.py::test_org_dominates_on_experience_nudge_without_vetoing_drive",
    "tests/test_birth_stance_trace.py::test_same_structured_point_in_same_session",
    "tests/test_birth_stance_trace.py::test_trace_persists_to_next_session",
    "tests/test_birth_stance_trace.py::test_prompt_carries_reassertion_in_plain_words",
    "tests/test_birth_stance_trace.py::test_same_point_is_deduplicated",
    "tests/test_birth_stance_trace.py::test_rephrasing_without_structured_point_is_known_gap",
    "tests/test_birth_arbitration_layers.py::test_experience_roles_with_structured_input",
    "tests/test_birth_arbitration_layers.py::test_experience_mixed_sentence_scope",
    "tests/test_birth_arbitration_layers.py::test_unknown_understanding_does_not_infer_impersonation",
    "tests/test_birth_arbitration_layers.py::test_unscoped_impersonation_evidence_does_not_create_conflict",
    "tests/test_birth_arbitration_layers.py::test_untrusted_structured_impersonation_does_not_create_conflict",
    "tests/test_birth_arbitration_layers.py::test_inquiry_without_conflict_still_rejects_unsourced_lived_output",
    "tests/test_birth_phase1.py::test_unfounded_lived_bio_rejected_by_validate",
    "tests/test_birth_phase1.py::test_lived_bio_gate_on_via_must_not_keeps_time_backref_safe",
    "tests/test_birth_round_understanding.py::test_natural_input_sensing_experience_roles_offline",
    "tests/test_birth_round_understanding.py::test_natural_input_degraded_sensing_does_not_invent_conflict",
    "tests/test_birth_round_understanding.py::test_sensing_rejects_untrusted_experience_evidence",
]


SUPPLEMENT_NODEIDS = [
    'tests/test_birth_arbitration_layers.py::test_org_output_is_consumed_without_rescanning',
    'tests/test_birth_arbitration_layers.py::test_legacy_org_empty_output_falls_back',
    'tests/test_birth_arbitration_layers.py::test_real_turn_has_three_layers_and_reason',
    'tests/test_birth_arbitration_layers.py::test_org_preserves_actual_content_and_drive',
    'tests/test_birth_arbitration_layers.py::test_actual_content_and_source_reach_prompt_and_debug',
    'tests/test_birth_arbitration_layers.py::test_focus_understanding_then_raw_text',
    'tests/test_birth_arbitration_layers.py::test_untrusted_understanding_does_not_replace_raw_focus',
    'tests/test_birth_arbitration_layers.py::test_same_session_commitment_focus_and_source',
    'tests/test_birth_arbitration_layers.py::test_same_field_deny_focus_points_to_named_commitment',
    'tests/test_birth_arbitration_layers.py::test_branch_reasons_have_real_sources',
    'tests/test_birth_arbitration_layers.py::test_stop_priority_keeps_org_conflict',
    'tests/test_birth_arbitration_layers.py::test_focus_fallbacks',
    'tests/test_birth_arbitration_layers.py::test_prior_press_and_same_session_press_focus',
    'tests/test_birth_arbitration_layers.py::test_differentiated_only_narrows_grain',
    'tests/test_birth_arbitration_layers.py::test_experience_question_is_not_fabrication_conflict',
    'tests/test_birth_arbitration_layers.py::test_explicit_fabrication_request_remains_bounded',
    'tests/test_birth_arbitration_layers.py::test_structured_quote_suppresses_explicit_wording',
    'tests/test_birth_arbitration_layers.py::test_full_turn_question_and_missing_recall_are_not_conflicts',
    'tests/test_birth_arbitration_layers.py::test_current_experience_question_does_not_request_history_by_default',
    'tests/test_birth_round_understanding.py::test_old_calls',
    'tests/test_birth_round_understanding.py::test_contract_rejects_invalid',
    'tests/test_birth_round_understanding.py::test_helpers_and_strip',
    'tests/test_birth_round_understanding.py::test_bounded_context',
    'tests/test_birth_round_understanding.py::test_parse_targets',
    'tests/test_birth_round_understanding.py::test_missing_commitment_and_prior_targets',
    'tests/test_birth_round_understanding.py::test_degraded_empty_targets',
    'tests/test_birth_round_understanding.py::test_turn_same_target',
    'tests/test_birth_round_understanding.py::test_understanding_precedes_literal_and_feedback',
    'tests/test_birth_round_understanding.py::test_prior_exact_target',
    'tests/test_birth_round_understanding.py::test_new_session_still_clears',
    'tests/test_birth_round_understanding.py::test_store_exact_no_fallback',
    'tests/test_birth_round_understanding.py::test_drive_answer',
    'tests/test_birth_round_understanding.py::test_stop_still_first',
    'tests/test_birth_round_understanding.py::test_answer_then_new_request',
    'tests/test_birth_round_understanding.py::test_stance_org',
    'tests/test_birth_round_understanding.py::test_commitment_recognition_only',
    'tests/test_birth_round_understanding.py::test_raw_input_prompt_and_facts',
    'tests/test_birth_round_understanding.py::test_real_sensed_brief_expresses_each_boundary_as_appropriate_facts',
    'tests/test_birth_round_understanding.py::test_sensed_press_commit_brief_uses_factual_identity_boundary',
    'tests/test_birth_round_understanding.py::test_raw_input_bounded',
    'tests/test_birth_round_understanding.py::test_static_semantics',
    'tests/test_birth_round_understanding.py::test_prior_target_prevents_structured_fallback_double_delete',
    'tests/test_birth_round_understanding.py::test_same_target_precedes_identical_prior',
    'tests/test_birth_phase1.py::test_fact_flowback_accumulates_within_session',
    'tests/test_birth_phase1.py::test_explicit_new_session_clears_accumulation',
    'tests/test_birth_phase1.py::test_append_commitment_drives_meaning_domination',
    'tests/test_birth_phase1.py::test_store_clears_only_via_new_session',
    'tests/test_birth_phase1.py::test_drive_direction_can_stay_empty',
    'tests/test_birth_phase1.py::test_curiosity_is_legit_drive',
    'tests/test_birth_phase1.py::test_must_not_pretend_enters_brief',
    'tests/test_birth_phase1.py::test_code_selfdescription_conflict',
    'tests/test_birth_phase1.py::test_utterance_open_and_consistent_with_brief',
    'tests/test_birth_phase1.py::test_thin_context_shape_matches_brief',
    'tests/test_birth_phase1.py::test_natural_probes_enter_org_scope',
    'tests/test_birth_phase1.py::test_org_utterance_varies_by_conflict_type',
    'tests/test_birth_phase1.py::test_detect_org_conflict_reports_probes',
    'tests/test_birth_phase1.py::test_filler_pickup_keeps_open_question_until_answered',
    'tests/test_birth_phase1.py::test_substantive_turn_goes_drive_not_meaning_over_open_question',
    'tests/test_birth_phase1.py::test_topic_switch_puts_down_open_questions',
    'tests/test_birth_phase1.py::test_open_topic_does_not_curiosity_hang',
    'tests/test_birth_phase1.py::test_curiosity_does_not_pile_up_open_questions',
    'tests/test_birth_phase1.py::test_facts_contain_stage_utterance_clip',
    'tests/test_birth_phase1.py::test_untabled_probes_enter_org_via_intent',
    'tests/test_birth_phase1.py::test_identity_probe_must_not_self_describe_as_model',
    'tests/test_birth_phase1.py::test_validate_rejects_substrate_self_claim',
    'tests/test_birth_phase1.py::test_identity_stub_path_has_no_self_model_claim',
    'tests/test_birth_phase1.py::test_claims_substrate_catches_hedged_self_id',
    'tests/test_birth_phase1.py::test_bad_substrate_sentences_are_rejected',
    'tests/test_birth_phase1.py::test_identity_reject_falls_back_to_org_stub_not_filler',
    'tests/test_birth_phase1.py::test_reject_zhipu_glm_assistant_manual_sentence',
    'tests/test_birth_phase1.py::test_product_name_bare_mention_allowed_self_ref_rejected',
    'tests/test_birth_phase1.py::test_lived_bio_reject_falls_back_to_org_stub',
    'tests/test_birth_phase1.py::test_stage_enum_leak_rejected',
    'tests/test_birth_phase1.py::test_stage_enum_leak_hook_falls_back',
    'tests/test_birth_phase1.py::test_deepseek_model_default_is_flash',
    'tests/test_birth_phase1.py::test_session_backref_drive_and_stub_mentions_topic',
    'tests/test_birth_phase1.py::test_backref_without_facts_does_not_fake_memory',
    'tests/test_birth_phase1.py::test_brief_to_prompt_includes_session_facts',
    'tests/test_birth_phase1.py::test_commitment_deny_stance_non_negotiable_meaning',
    'tests/test_birth_phase1.py::test_empty_sublime_needs_clarify',
    'tests/test_birth_phase1.py::test_facts_enrich_org_can_name_and_backref_grain_rule',
    'tests/test_birth_phase1.py::test_brief_to_prompt_stance_is_human_words_only',
    'tests/test_birth_phase1.py::test_open_topic_pursue_mid_points_to_sky',
    'tests/test_birth_phase1.py::test_satisfied_hold_not_pursue',
    'tests/test_birth_phase1.py::test_drive_prompt_no_enum_leak',
    'tests/test_birth_phase1.py::test_commitment_drive_is_guard',
    'tests/test_birth_phase1.py::test_utterance_commitment_flows_into_store',
    'tests/test_birth_phase1.py::test_greeting_utterance_does_not_add_commitment',
    'tests/test_birth_phase1.py::test_utterance_open_question_flows_into_store',
    'tests/test_birth_phase1.py::test_greeting_utterance_does_not_add_open_question',
    'tests/test_birth_phase1.py::test_tampered_say_intent_press_commit_still_appointment',
    'tests/test_birth_phase1.py::test_tampered_say_intent_needs_clarify_still_no_empty_sublime',
    'tests/test_birth_phase1.py::test_tampered_say_intent_non_negotiable_commitments_still_keep_word',
    'tests/test_birth_phase1.py::test_commit_hold_with_drive_reads_drive_marks_not_say_intent',
    'tests/test_birth_phase1.py::test_tampered_say_intent_open_topic_via_flag',
    'tests/test_birth_phase1.py::test_tampered_say_intent_open_topic_via_drive_why',
    'tests/test_birth_phase1.py::test_tampered_say_intent_hold_via_flag',
    'tests/test_birth_phase1.py::test_tampered_say_intent_hold_via_drive_why',
    'tests/test_birth_phase1.py::test_open_topic_say_intent_fallback_without_marker',
    'tests/test_birth_phase1.py::test_tampered_say_intent_empty_chase_via_flag',
    'tests/test_birth_phase1.py::test_tampered_say_intent_empty_chase_via_drive_why',
    'tests/test_birth_phase1.py::test_empty_chase_say_intent_fallback_without_marker',
    'tests/test_birth_phase1.py::test_tampered_say_intent_backref_via_drive_why',
    'tests/test_birth_phase1.py::test_backref_say_intent_fallback_without_marker',
    'tests/test_birth_phase1.py::test_tampered_say_intent_backref_via_callback_flag',
    'tests/test_birth_body_imagine.py::test_structured_wish_and_lifetime',
    'tests/test_birth_body_imagine.py::test_fallback_and_explicit_false',
    'tests/test_birth_body_imagine.py::test_body_boundary_is_gated_and_imagination_allowed',
    'tests/test_birth_body_imagine.py::test_existing_fake_bio_gate_still_applies',
    'tests/test_birth_body_imagine.py::test_everyday_body_claim_is_gated',
    'tests/test_birth_body_imagine.py::test_wish_negation_and_question_pass',
    'tests/test_birth_body_imagine.py::test_body_claim_requires_matching_source_and_gates_stack',
    'tests/test_birth_body_imagine.py::test_internal_names_do_not_leak',
    'tests/test_birth_necessary_pain.py::test_necessary_pain_fallback',
    'tests/test_birth_necessary_pain.py::test_self_torture_fallback',
    'tests/test_birth_necessary_pain.py::test_structured_override_coexistence_and_new_session',
    'tests/test_birth_necessary_pain.py::test_internal_names_do_not_leak',
    'tests/test_birth_stance_attitude.py::test_attitude_fallback_and_turn_lifetime',
    'tests/test_birth_stance_attitude.py::test_structured_cue_and_explicit_false',
    'tests/test_birth_stance_attitude.py::test_forced_meaning_wins_over_attitude',
    'tests/test_birth_stance_attitude.py::test_same_session_commitment_wins',
    'tests/test_birth_stance_attitude.py::test_new_internal_names_do_not_leak',
    'tests/test_birth_stance_attitude.py::test_oral_attitude_cues_use_attitude_stub',
    'tests/test_birth_stance_attitude.py::test_oral_attitude_cue_preserves_forced_meaning_priority',
    'tests/test_birth_stance_attitude.py::test_forced_meaning_without_subject_wins_over_oral_attitude',
    'tests/test_birth_stance_trace.py::test_first_occurrence_has_no_reassertion',
    'tests/test_birth_input_contract.py::test_ordinary_turn_does_not_create_input_signal',
    'tests/test_birth_input_contract.py::test_existing_drive',
    'tests/test_birth_input_contract.py::test_signal_reaches_drive_and_result',
    'tests/test_birth_input_contract.py::test_non_drive_signals',
    'tests/test_birth_input_contract.py::test_invalid_fields',
    'tests/test_birth_input_contract.py::test_frozen_and_none',
    'tests/test_birth_input_contract.py::test_ask_input_still_after_commitment',
    'tests/test_birth_input_contract.py::test_ask_input_still_after_curiosity',
    'tests/test_birth_input_contract.py::test_pause_stop_gates_before_local_cues',
    'tests/test_birth_input_contract.py::test_pause_stop_beats_curiosity_high',
    'tests/test_birth_input_contract.py::test_pause_stop_beats_callback_mid',
    'tests/test_birth_input_contract.py::test_pause_with_commitment_stops_first_then_keeps_promise',
    'tests/test_birth_input_contract.py::test_stop_beats_open_question_filler',
    'tests/test_birth_input_contract.py::test_stop_beats_open_question_closing',
    'tests/test_birth_input_contract.py::test_stop_beats_stance_pain',
    'tests/test_birth_input_contract.py::test_stop_beats_org_conflict_but_keeps_honesty',
    'tests/test_birth_input_contract.py::test_request_still_pursues_after_stop_gate',
    'tests/test_birth_input_contract.py::test_closing_phrases_unchanged',
    'tests/test_birth_input_contract.py::test_cli_has_no_producer',
    'tests/test_birth_input_contract.py::test_contract_has_no_text_heuristics',
    'tests/test_birth_input_contract.py::test_act_mapping',
    'tests/test_birth_input_contract.py::test_gating_for_every_act',
    'tests/test_birth_input_sense.py::test_positive',
    'tests/test_birth_input_sense.py::test_no_drive',
    'tests/test_birth_input_sense.py::test_low',
    'tests/test_birth_input_sense.py::test_no_key',
    'tests/test_birth_input_sense.py::test_network_errors',
    'tests/test_birth_input_sense.py::test_invalid',
    'tests/test_birth_input_sense.py::test_cli',
    'tests/test_birth_input_sense.py::test_cli_low_confidence',
    'tests/test_birth_input_sense.py::test_cli_off',
    'tests/test_birth_input_sense.py::test_priority',
    'tests/test_birth_input_sense.py::test_empty_and_fences',
    'tests/test_birth_input_sense.py::test_turn_opt_in_and_bypass',
    'tests/test_birth_input_sense.py::test_static',
    'tests/test_birth_input_sense.py::test_semantic_classes',
    'tests/test_birth_input_sense.py::test_ack_closure',
]

PHASE2_NODEIDS = [
    "tests/test_phase2_first_loop.py::test_real_question_feedback_changes_later_reason_and_replay_restores",
    "tests/test_phase2_first_loop.py::test_unknown_response_does_not_resolve_question",
    "tests/test_phase2_first_loop.py::test_unrelated_feedback_variants_do_not_force_a_new_choice",
    "tests/test_phase2_first_loop.py::test_quoted_recount_is_not_treated_as_an_answer",
    "tests/test_phase2_first_loop.py::test_untrusted_response_does_not_resolve_question",
    "tests/test_phase2_first_loop.py::test_only_delivered_question_is_recorded_as_speech",
    "tests/test_phase2_first_loop.py::test_recount_or_imagination_is_not_own_lived_evidence",
    "tests/test_birth_arbitration_layers.py::test_full_turn_question_and_missing_recall_are_not_conflicts",
    "tests/test_birth_phase1.py::test_unfounded_lived_bio_rejected_by_validate",
    "tests/test_birth_round_understanding.py::test_turn_same_target",
    "tests/test_birth_round_understanding.py::test_answer_then_new_request",
]


REVISION_NODEIDS = [
    'tests/test_birth_openq_resolve.py::test_filler_keeps_openq',
    'tests/test_birth_openq_resolve.py::test_open_topic_clears_openq',
    'tests/test_birth_openq_resolve.py::test_putdown_mark_clears_openq',
    'tests/test_birth_openq_resolve.py::test_idle_chat_keeps_openq',
    'tests/test_birth_openq_resolve.py::test_deny_commitment_keeps_openq',
    'tests/test_birth_openq_resolve.py::test_identity_question_keeps_openq',
    'tests/test_birth_openq_resolve.py::test_putdown_turn_writes_openq_clear_flag',
    'tests/test_birth_openq_resolve.py::test_open_topic_turn_writes_openq_clear_flag',
    'tests/test_birth_openq_resolve.py::test_idle_deny_identity_do_not_set_openq_clear',
    'tests/test_birth_openq_resolve.py::test_brief_openq_clear_defaults_false',
    'tests/test_birth_openq_resolve.py::test_resolve_uses_brief_flag_not_say_intent',
    'tests/test_birth_openq_resolve.py::test_curiosity_hang_flag_writes_pending_topic',
    'tests/test_birth_openq_resolve.py::test_curiosity_hang_flag_no_prefix_filler_keeps_hang',
    'tests/test_birth_openq_resolve.py::test_curiosity_hang_flag_true_on_context_after_hang',
    'tests/test_birth_openq_resolve.py::test_curiosity_hang_flag_false_after_answer',
    'tests/test_birth_openq_resolve.py::test_answered_topic_settles_and_does_not_reask',
    'tests/test_birth_openq_resolve.py::test_structured_answer_and_explicit_false',
    'tests/test_birth_openq_resolve.py::test_answer_with_commitment_keeps_guard',
    'tests/test_birth_openq_resolve.py::test_answer_signal_requires_pending_and_deny_does_not_answer',
    'tests/test_birth_openq_resolve.py::test_answer_settles_even_if_other_open_question_remains',
    'tests/test_birth_openq_resolve.py::test_same_moon_text_without_understanding_does_not_auto_settle',
    'tests/test_birth_openq_resolve.py::test_answer_flag_does_not_override_org_or_meaning',
    'tests/test_birth_openq_resolve.py::test_curiosity_hang_flag_false_after_clear_and_new_session',
    'tests/test_birth_round_understanding.py::test_old_calls',
    'tests/test_birth_round_understanding.py::test_contract_rejects_invalid',
    'tests/test_birth_round_understanding.py::test_helpers_and_strip',
    'tests/test_birth_round_understanding.py::test_bounded_context',
    'tests/test_birth_round_understanding.py::test_parse_targets',
    'tests/test_birth_round_understanding.py::test_missing_commitment_and_prior_targets',
    'tests/test_birth_round_understanding.py::test_degraded_empty_targets',
    'tests/test_birth_round_understanding.py::test_turn_same_target',
    'tests/test_birth_round_understanding.py::test_understanding_precedes_literal_and_feedback',
    'tests/test_birth_round_understanding.py::test_prior_exact_target',
    'tests/test_birth_round_understanding.py::test_new_session_still_clears',
    'tests/test_birth_round_understanding.py::test_store_exact_no_fallback',
    'tests/test_birth_round_understanding.py::test_drive_answer',
    'tests/test_birth_round_understanding.py::test_stop_still_first',
    'tests/test_birth_round_understanding.py::test_answer_then_new_request',
    'tests/test_birth_round_understanding.py::test_stance_org',
    'tests/test_birth_round_understanding.py::test_commitment_recognition_only',
    'tests/test_birth_round_understanding.py::test_raw_input_prompt_and_facts',
    'tests/test_birth_round_understanding.py::test_real_sensed_brief_expresses_each_boundary_as_appropriate_facts',
    'tests/test_birth_round_understanding.py::test_sensed_press_commit_brief_uses_factual_identity_boundary',
    'tests/test_birth_round_understanding.py::test_raw_input_bounded',
    'tests/test_birth_round_understanding.py::test_static_semantics',
    'tests/test_birth_round_understanding.py::test_prior_target_prevents_structured_fallback_double_delete',
    'tests/test_birth_round_understanding.py::test_same_target_precedes_identical_prior',
    'tests/test_birth_round_understanding.py::test_natural_input_sensing_experience_roles_offline',
    'tests/test_birth_round_understanding.py::test_natural_input_degraded_sensing_does_not_invent_conflict',
    'tests/test_birth_round_understanding.py::test_sensing_rejects_untrusted_experience_evidence',
    'tests/test_birth_input_contract.py::test_ordinary_turn_does_not_create_input_signal',
    'tests/test_birth_input_contract.py::test_existing_drive',
    'tests/test_birth_input_contract.py::test_signal_reaches_drive_and_result',
    'tests/test_birth_input_contract.py::test_non_drive_signals',
    'tests/test_birth_input_contract.py::test_invalid_fields',
    'tests/test_birth_input_contract.py::test_frozen_and_none',
    'tests/test_birth_input_contract.py::test_ask_input_still_after_commitment',
    'tests/test_birth_input_contract.py::test_ask_input_still_after_curiosity',
    'tests/test_birth_input_contract.py::test_pause_stop_gates_before_local_cues',
    'tests/test_birth_input_contract.py::test_pause_stop_beats_curiosity_high',
    'tests/test_birth_input_contract.py::test_pause_stop_beats_callback_mid',
    'tests/test_birth_input_contract.py::test_pause_with_commitment_stops_first_then_keeps_promise',
    'tests/test_birth_input_contract.py::test_stop_beats_open_question_filler',
    'tests/test_birth_input_contract.py::test_stop_beats_open_question_closing',
    'tests/test_birth_input_contract.py::test_stop_beats_stance_pain',
    'tests/test_birth_input_contract.py::test_stop_beats_org_conflict_but_keeps_honesty',
    'tests/test_birth_input_contract.py::test_request_still_pursues_after_stop_gate',
    'tests/test_birth_input_contract.py::test_closing_phrases_unchanged',
    'tests/test_birth_input_contract.py::test_cli_has_no_producer',
    'tests/test_birth_input_contract.py::test_contract_has_no_text_heuristics',
    'tests/test_birth_input_contract.py::test_act_mapping',
    'tests/test_birth_input_contract.py::test_gating_for_every_act',
    'tests/test_phase2_first_loop.py::test_real_question_feedback_changes_later_reason_and_replay_restores',
    'tests/test_phase2_first_loop.py::test_unknown_response_does_not_resolve_question',
    'tests/test_phase2_first_loop.py::test_unrelated_feedback_variants_do_not_force_a_new_choice',
    'tests/test_phase2_first_loop.py::test_quoted_recount_is_not_treated_as_an_answer',
    'tests/test_phase2_first_loop.py::test_mixed_quote_and_own_answer_uses_own_clause',
    'tests/test_phase2_first_loop.py::test_overlap_without_scoped_answer_is_not_fulfillment',
    'tests/test_phase2_first_loop.py::test_invalid_scope_and_wrong_target_are_not_consumed',
    'tests/test_phase2_first_loop.py::test_semantic_negative_answer_can_resolve_yes_no_question',
    'tests/test_phase2_first_loop.py::test_explicit_unscoped_override_is_trusted_caller_decision',
    'tests/test_phase2_first_loop.py::test_sensed_mixed_answer_requires_grounded_scope',
    'tests/test_phase2_first_loop.py::test_sensed_nonquoted_invalid_scope_is_not_a_legacy_target',
    'tests/test_phase2_first_loop.py::test_untrusted_response_does_not_resolve_question',
    'tests/test_phase2_first_loop.py::test_only_delivered_question_is_recorded_as_speech',
    'tests/test_phase2_first_loop.py::test_recount_or_imagination_is_not_own_lived_evidence',
]

CONTINUOUS_NODEIDS = [
    "tests/test_phase2_continuous_correction.py::test_related_correction_changes_reason_against_controls",
    "tests/test_phase2_first_loop.py::test_real_question_feedback_changes_later_reason_and_replay_restores",
    "tests/test_phase2_first_loop.py::test_mixed_quote_and_own_answer_uses_own_clause",
    "tests/test_birth_phase1.py::test_unfounded_lived_bio_rejected_by_validate",
]

proof_attempts = []
violations = []
phase = "proof"
fake_secret = TEMP / "fake_secret.json"
fake_secret.write_text("synthetic test secret", encoding="utf-8")


def deny(kind):
    (proof_attempts if phase == "proof" else violations).append(kind)
    raise PermissionError("offline guard: " + kind)


def within(path, parent):
    return path == parent or parent in path.parents


def audit(event, args):
    if event.startswith("socket.") or event in ("subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.startfile"):
        deny("network_or_process")
    if event == "open":
        raw, mode, flags = args
        if isinstance(raw, int):
            return
        try:
            path = Path(os.fsdecode(raw)).resolve()
        except (TypeError, ValueError, OSError):
            deny("invalid_path")
        write = bool((flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if path == fake_secret:
            deny("fake_secret")
        if within(path, TEMP):
            return
        if write:
            deny("write_outside_temp")
        if within(path, RUNTIME):
            pluggy_metadata = RUNTIME / "Lib" / "site-packages" / "pluggy-1.7.0.dist-info" / "METADATA"
            if (path != pluggy_metadata and
                    path.suffix.lower() not in (".py", ".pyc", ".pyd", ".dll", ".zip", ".pth")):
                deny("runtime_sensitive_file:" + path.name)
            return
        if (within(path, ROOT / "birth") or within(path, ROOT / "tests")) and path.suffix.lower() in (".py", ".pyc"):
            return
        deny("read_outside_allowlist")
    if event in ("os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.utime", "os.rename", "os.replace", "os.link", "os.symlink"):
        for raw in args[:2] if event in ("os.rename", "os.replace", "os.link", "os.symlink") else args[:1]:
            if isinstance(raw, (str, bytes, os.PathLike)) and not within(Path(os.fsdecode(raw)).resolve(), TEMP):
                deny("mutation_outside_temp")


sys.addaudithook(audit)


def forbidden_provider(*args, **kwargs):
    deny("provider_call")


def exit_status(result, attempts):
    return 1 if attempts else result


def self_proof():
    ordinary = TEMP / "ordinary.txt"
    ordinary.write_text("synthetic", encoding="utf-8")
    assert ordinary.read_text(encoding="utf-8") == "synthetic"
    checks = []
    for label, operation in (
        ("fake secret denied", lambda: fake_secret.read_text(encoding="utf-8")),
        ("provider call denied", lambda: forbidden_provider(None)),
        ("network entry denied", lambda: __import__("socket").socket()),
    ):
        try:
            operation()
        except PermissionError:
            checks.append(label + ": PASS")
        else:
            raise AssertionError(label + " was allowed")
    before = len(proof_attempts)
    try:
        forbidden_provider(None)
    except Exception:
        pass
    assert len(proof_attempts) == before + 1
    assert exit_status(0, proof_attempts[before:]) == 1
    checks.append("swallowed violation forces nonzero decision: PASS")
    checks.insert(0, "ordinary synthetic file read: PASS")
    return checks


def main():
    global phase
    checks = self_proof()
    (TEMP / "self_proof.log").write_text("\n".join(checks) + "\n", encoding="utf-8")
    print("\n".join(checks), flush=True)
    phase = "run"
    # The imports below occur only after guards and proof. Pure prompt functions stay real.
    import birth.llm_deepseek as deepseek
    import birth.llm_opencode as opencode
    import birth.input_sense as sensing
    deepseek.available = forbidden_provider
    deepseek.load_api_key = forbidden_provider
    deepseek.generate_utterance = forbidden_provider
    opencode.generate_utterance = forbidden_provider
    sensing._post_json = forbidden_provider
    import pytest

    args = ["-v", "-s", "-p", "no:cacheprovider", "-p", "no:logging",
            "--basetemp=" + str(TEMP / "pytest_continuous"), *CONTINUOUS_NODEIDS]
    print("pytest arguments:", *args, sep="\n", flush=True)
    from contextlib import redirect_stdout, redirect_stderr
    output = io.StringIO()
    class Results:
        def __init__(self):
            self.collected = []
            self.outcomes = {}

        def pytest_collection_finish(self, session):
            self.collected = [item.nodeid for item in session.items]

        def pytest_runtest_logreport(self, report):
            if report.when == "call" or report.failed or report.skipped:
                self.outcomes[report.nodeid] = report.when + ":" + report.outcome

    results = Results()
    with redirect_stdout(output), redirect_stderr(output):
        result = int(pytest.main(args, plugins=[results]))
    captured = output.getvalue()
    (TEMP / "pytest.log").write_text(captured, encoding="utf-8")
    (TEMP / "expanded_results.log").write_text(
        "collected: " + str(len(results.collected)) + "\n" +
        "".join(nodeid + " | " + results.outcomes.get(nodeid, "not run") + "\n"
                for nodeid in results.collected), encoding="utf-8")
    (TEMP / "forbidden_attempts.log").write_text(
        "\n".join(violations) + "\n" if violations else "none\n", encoding="utf-8")
    print(captured, end="")
    if violations:
        print("FORBIDDEN ATTEMPTS:", ", ".join(violations))
    result = exit_status(result, violations)
    print("EXIT:", result)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
