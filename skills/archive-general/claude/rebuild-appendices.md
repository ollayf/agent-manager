# Rebuild appendices

Generated from this rebuild. The recovered archive-icloud-guide.md remains unchanged.

## E — collected tests

### test_icloud_archive.py (94 cases)

- `test_folder_sync_moves_files_and_parks_folders`
- `test_later_sync_adds_only_new_files`
- `test_archive_is_sync_without_update`
- `test_read_file_and_folder_in_place`
- `test_restore_one_file_from_a_folder`
- `test_file_over_limit_is_compressed_into_one_part`
- `test_incompressible_file_over_limit_is_split`
- `test_small_file_stays_raw`
- `test_internal_looking_names_roundtrip[names0]`
- `test_internal_looking_names_roundtrip[names1]`
- `test_internal_looking_names_roundtrip[names2]`
- `test_case_only_clash_refused`
- `test_recently_changed_file_is_skipped`
- `test_folder_with_cursor_file_is_left_alone`
- `test_file_named_alone_in_busy_folder_is_skipped`
- `test_open_file_is_skipped`
- `test_database_with_sidecar_is_skipped`
- `test_open_sqlite_connection_is_skipped`
- `test_changed_file_reported_then_updated_with_old_copy_kept`
- `test_status_reports_every_state`
- `test_status_is_read_only`
- `test_nested_claude_md_does_not_split_the_index`
- `test_existing_icloud_md_wins_over_git`
- `test_explicit_repo_is_used_as_is`
- `test_exclude_globs_and_prefixes`
- `test_refusals_have_no_side_effects`
- `test_no_delete_rule_requires_flag`
- `test_symlink_inside_folder_is_skipped`
- `test_crash_during_sync_is_recoverable[after-copy-False]`
- `test_crash_during_sync_is_recoverable[after-copy-True]`
- `test_crash_during_sync_is_recoverable[after-rename-False]`
- `test_crash_during_sync_is_recoverable[after-rename-True]`
- `test_crash_during_sync_is_recoverable[after-index-False]`
- `test_crash_during_sync_is_recoverable[after-index-True]`
- `test_crash_during_sync_is_recoverable[after-delete-False]`
- `test_crash_during_sync_is_recoverable[after-delete-True]`
- `test_crash_during_restore_is_recoverable[restore-after-rename]`
- `test_crash_during_restore_is_recoverable[restore-after-index]`
- `test_rerun_sync_adopts_identical_copy_left_by_a_crash`
- `test_torn_manifest_line_is_tolerated_and_fixed`
- `test_deleted_index_is_rebuilt_from_manifest`
- `test_verify_never_touches_a_changed_file`
- `test_unknown_orphan_left_alone`
- `test_parallel_syncs_of_different_folders_lose_nothing`
- `test_parallel_syncs_of_same_folder_end_consistent`
- `test_summary_counts_and_space_note`
- `test_upload_status_and_evict_do_not_apply_outside_icloud`
- `test_list_filters_by_path`
- `test_records_and_manifest_carry_versions`
- `test_skill_md_version_matches_script`
- `test_new_archive_is_nested_under_repos`
- `test_repo_outside_home_nests_under_abs`
- `test_full_restore_removes_registry_entry`
- `test_same_path_different_repo_refused`
- `test_fresh_clone_finds_its_archive_through_the_registry`
- `test_format_from_the_future_is_refused`
- `test_tampered_history_is_not_run`
- `test_history_hashes_match`
- `test_import_mirror_with_manifest`
- `test_import_mirror_md5_mismatch_moves_nothing_for_that_file`
- `test_import_mirror_refuses_unlisted_file_and_collisions`
- `test_import_mirror_without_manifest`
- `test_import_mirror_crash_resumes`
- `test_read_through_the_old_hand_made_path`
- `test_import_split_round_trip`
- `test_import_split_refuses_bad_hashes_and_moves_nothing[part]`
- `test_import_split_refuses_bad_hashes_and_moves_nothing[stream]`
- `test_import_split_crash_resumes`
- `test_import_refuses_a_folder_inside_claude_archive`
- `test_remove_empty_tree_never_removes_a_real_file`
- `test_import_accept_mismatch_only_for_the_named_file`
- `test_import_never_follows_a_symlink`
- `test_plain_read_of_a_huge_compressed_file_needs_full`
- `test_old_path_inside_a_split_import_never_reassembles_the_original`
- `test_v1_and_v2_coexist`
- `test_old_v1_script_still_reads_a_v2_index`
- `test_v2_restores_every_v1_form`
- `test_sync_skips_files_inside_a_v1_entry`
- `test_restore_of_file_inside_v1_dir_names_the_dir`
- `test_v1_entry_in_v2_area_blocks_sync`
- `test_upgrade_plan_changes_nothing`
- `test_upgrade_repo_relocates_and_converts_every_v1_row`
- `test_upgrade_unpacks_small_pack_raw`
- `test_registry_scan_registers_v1_archive_without_changing_icloud_md`
- `test_upgrade_one_folder_only`
- `test_upgrade_all_reaches_a_repo_that_is_not_here`
- `test_read_through_an_old_icloud_path_after_relocate`
- `test_broken_v1_reader_names_the_history_fallback`
- `test_upgrade_waits_for_icloud_upload`
- `test_verify_reports_ghosts_left_at_an_old_root`
- `test_v200_archive_read_and_restored_through_its_own_history`
- `test_crash_during_upgrade_is_recoverable[relocate-after-rename]`
- `test_crash_during_upgrade_is_recoverable[relocate-after-index]`
- `test_crash_during_upgrade_is_recoverable[upgrade-after-move]`

### test_parked_folders.py (57 cases)

- `test_sync_parks_folders_that_hold_only_archived_files`
- `test_partly_archived_folder_stays`
- `test_next_month_merges_into_the_parked_tree`
- `test_folders_without_records_follow_their_parent_both_ways`
- `test_sync_of_single_files_parks_their_folder`
- `test_empty_folder_without_archived_files_never_moves`
- `test_ds_store_is_carried_and_the_run_converges`
- `test_nfd_folder_names_park_and_restore`
- `test_sync_of_the_park_folder_is_skipped_not_refused`
- `test_keep_file_pins_its_folder`
- `test_restore_one_file_brings_back_its_folder_only`
- `test_full_restore_removes_the_park_folder`
- `test_restore_works_when_the_park_folder_was_deleted`
- `test_paths_under_the_park_folder_mean_the_same_path`
- `test_via_history_runs_from_a_subfolder`
- `test_age_guard_keeps_a_folder_changed_by_someone_else`
- `test_a_folder_changed_just_before_the_run_stays`
- `test_ledger_spots_another_program_between_this_runs_changes`
- `test_folder_in_use_is_kept`
- `test_the_scripts_own_working_folder_is_kept`
- `test_no_folder_moves_when_lsof_cannot_answer[missing]`
- `test_no_folder_moves_when_lsof_cannot_answer[fails]`
- `test_no_folder_moves_when_lsof_cannot_answer[hangs]`
- `test_symlink_into_a_folder_keeps_it`
- `test_excluded_folder_stays`
- `test_nested_repo_and_submodule_link_keep_their_folders`
- `test_a_file_written_during_the_move_keeps_its_folder`
- `test_park_folder_must_be_a_plain_folder[symlink]`
- `test_park_folder_must_be_a_plain_folder[file]`
- `test_park_folder_must_be_a_plain_folder[dangling]`
- `test_files_in_the_park_folder_are_never_touched`
- `test_a_taken_name_keeps_folders_in_place[_ARCHIVE/]`
- `test_a_taken_name_keeps_folders_in_place[_archive/notes.txt]`
- `test_deleted_index_is_rebuilt_with_the_line`
- `test_sync_while_the_icloud_index_is_newer_keeps_every_record`
- `test_crash_during_a_move_converges[tidy-after-mkdir]`
- `test_crash_during_a_move_converges[tidy-after-rmdir]`
- `test_crash_while_moving_back_converges`
- `test_import_into_a_parked_repo_parks_the_structure`
- `test_remove_empty_tree_keeps_an_icloud_placeholder`
- `test_import_keeps_icloud_placeholders`
- `test_tidy_plan_is_read_only_and_tidy_refuses_an_old_repo`
- `test_old_release_restore_then_23_matches_a_23_restore`
- `test_repo_archived_by_221_keeps_folders_until_upgraded`
- `test_park_step_neither_waits_nor_refuses_while_an_upload_is_pending`
- `test_park_step_changes_nothing_in_icloud`
- `test_the_mirror_never_turns_on_parking`
- `test_upgrade_all_parks_each_repo_or_says_why_not`
- `test_records_under_the_name_refuse_it`
- `test_crash_after_the_setting_is_saved_converges`
- `test_setting_survives_v1_deleting_icloud_md`
- `test_release_200_on_a_parked_pure_v2_repo`
- `test_old_releases_work_on_a_parked_repo[2.1.0]`
- `test_old_releases_work_on_a_parked_repo[2.2.0]`
- `test_old_releases_work_on_a_parked_repo[2.2.1]`
- `test_random_operations_stay_consistent[1]`
- `test_random_operations_stay_consistent[2]`

### test_legacy_compat.py (68 cases)

- `test_file_roundtrip_preserves_bytes_mtime_mode`
- `test_dir_roundtrip_with_nested_empty_dir`
- `test_zero_byte_file`
- `test_multiple_paths_partial_failure_reports_each`
- `test_restore_recreates_missing_parents`
- `test_index_stays_sorted_and_light`
- `test_odd_names_roundtrip[with space/file name.csv]`
- `test_odd_names_roundtrip[emoji \U0001f4e6/\u2713.txt]`
- `test_odd_names_roundtrip[a|b.txt]`
- `test_odd_names_roundtrip[-leading-dash.txt]`
- `test_odd_names_roundtrip[deep/deep/deep/deep/deep/deep/deep/deep/deep/deep/deep/deep/deep/deep/deep/deep/deep/deep/deep/deep/long_long_long_long_long_long_long_long_long_long_long_long_long_long_long_long_long_long_long_long_.txt]`
- `test_unicode_nfd_archive_nfc_restore`
- `test_backtick_and_newline_refused`
- `test_case_only_clash_refused_on_case_insensitive_fs`
- `test_refusals_have_no_side_effects`
- `test_archiving_index_itself_refused`
- `test_no_project_root_refused`
- `test_non_git_root_from_claude_md`
- `test_non_git_explicit_repo`
- `test_already_archived_refused`
- `test_restore_refuses_to_overwrite_local`
- `test_archive_refuses_when_icloud_already_has_it`
- `test_restore_when_icloud_copy_missing`
- `test_run_from_subdir_stores_repo_relative`
- `test_same_dir_name_different_repos_get_different_ids`
- `test_same_remote_shares_id`
- `test_root_line_in_index_is_source_of_truth`
- `test_hand_written_prose_is_preserved`
- `test_malformed_index_refuses_everything`
- `test_large_file_is_packed_into_parts_and_restores_identically`
- `test_compressible_file_and_fast_mode`
- `test_small_sqlite_db_is_always_packed`
- `test_read_packed_decompresses_to_temp`
- `test_damaged_pack_refuses_restore_and_changes_nothing[corrupt]`
- `test_damaged_pack_refuses_restore_and_changes_nothing[missing]`
- `test_damaged_pack_refuses_restore_and_changes_nothing[manifest]`
- `test_open_file_refused`
- `test_sqlite_sidecar_refused`
- `test_no_delete_rule_requires_explicit_flag`
- `test_dir_with_large_file_refused`
- `test_not_enough_space_refused_up_front`
- `test_disk_fills_mid_copy_original_untouched[False]`
- `test_disk_fills_mid_copy_original_untouched[True]`
- `test_crash_during_archive_is_recoverable[after-copy-file]`
- `test_crash_during_archive_is_recoverable[after-copy-dir]`
- `test_crash_during_archive_is_recoverable[after-copy-packed]`
- `test_crash_during_archive_is_recoverable[after-rename-file]`
- `test_crash_during_archive_is_recoverable[after-rename-dir]`
- `test_crash_during_archive_is_recoverable[after-rename-packed]`
- `test_crash_during_archive_is_recoverable[after-index-file]`
- `test_crash_during_archive_is_recoverable[after-index-dir]`
- `test_crash_during_archive_is_recoverable[after-index-packed]`
- `test_crash_during_restore_is_recoverable[restore-after-rename]`
- `test_crash_during_restore_is_recoverable[restore-after-index]`
- `test_verify_never_touches_differing_copies`
- `test_unknown_orphan_left_alone`
- `test_finder_litter_is_ignored`
- `test_parallel_archives_of_different_files_lose_nothing`
- `test_parallel_archives_of_same_file_exactly_one_wins`
- `test_archive_restore_race_ends_consistent`
- `test_parallel_restores_of_different_files`
- `test_lock_timeout_refuses_cleanly`
- `test_archive_summary_confirms_files_from_disk`
- `test_restore_summary_after_last_entry_removes_index`
- `test_summary_counts_refusals`
- `test_upload_status_and_evict_do_not_apply_outside_icloud`
- `test_read_file_inside_archived_dir`
- `test_read_head_streams_packed`

### test_rebuild_regressions.py (40 cases)

- `test_builtin_v1_restore_literal_format[file]`
- `test_builtin_v1_restore_literal_format[dir]`
- `test_builtin_v1_restore_literal_format[pack]`
- `test_builtin_v1_upgrade_literal_format[file]`
- `test_builtin_v1_upgrade_literal_format[dir]`
- `test_builtin_v1_upgrade_literal_format[pack]`
- `test_builtin_v1_big_pack_stays_packed`
- `test_builtin_upgrade_crash_recovery[upgrade-after-move]`
- `test_builtin_upgrade_crash_recovery[park-after-setting]`
- `test_builtin_upgrade_crash_recovery[relocate-after-rename]`
- `test_builtin_upgrade_crash_recovery[relocate-after-index]`
- `test_scoped_upgrade_keeps_other_rows_and_layout`
- `test_v1_overlap_is_refused_and_inside_dir_restore_names_folder`
- `test_v1_registry_scan_preserves_prose_and_table`
- `test_v1_table_remains_above_v2_block`
- `test_upgrade_waits_before_any_nonpark_step`
- `test_upgrade_all_uses_remote_mirror_and_old_path_reads_follow`
- `test_named_junk_is_refused_without_side_effects[.keep]`
- `test_named_junk_is_refused_without_side_effects[.DS_Store]`
- `test_named_junk_is_refused_without_side_effects[.x.icloud]`
- `test_import_batch_saves_and_evicts_between_batches`
- `test_read_only_commands_do_not_settle_newer_mirror`
- `test_store_refuses_ambiguous_or_unsafe_records[unknown-op]`
- `test_store_refuses_ambiguous_or_unsafe_records[bad-middle-line]`
- `test_store_refuses_ambiguous_or_unsafe_records[unsafe-path]`
- `test_store_refuses_ambiguous_or_unsafe_records[root-mismatch]`
- `test_registry_unknown_fields_survive_updates`
- `test_run_log_records_help_and_usage_exits`
- `test_rebuild_random_round_trips[1]`
- `test_rebuild_random_round_trips[2]`
- `test_verify_finishes_a_partly_moved_v1_directory`
- `test_upgrade_alone_settles_an_interrupted_relocation`
- `test_failed_sync_with_durable_changes_compacts_both_indexes`
- `test_upgrade_and_main_versions_always_match`
- `test_import_cannot_create_records_for_the_indexes[mirror-ICLOUD.md]`
- `test_import_cannot_create_records_for_the_indexes[mirror-ICLOUD.manifest.jsonl]`
- `test_import_cannot_create_records_for_the_indexes[split-ICLOUD.md]`
- `test_import_cannot_create_records_for_the_indexes[split-ICLOUD.manifest.jsonl]`
- `test_inventory_allows_only_folder_and_finder_moves`
- `test_release_is_immutable_and_checks_its_own_sums`

## F — mutation pairings

| # | Guard | Test |
|---|---|---|
| 1 | root: nearest ICLOUD.md/CLAUDE.md instead of highest | `test_icloud_archive.py::test_nested_claude_md_does_not_split_the_index` |
| 2 | live guard: recent mtime ignored | `test_icloud_archive.py::test_recently_changed_file_is_skipped` |
| 3 | live guard: busy-folder markers ignored | `test_icloud_archive.py::test_folder_with_cursor_file_is_left_alone` |
| 4 | live guard: open files ignored | `test_icloud_archive.py::test_open_file_is_skipped` |
| 5 | live guard: SQLite sidecars ignored | `test_icloud_archive.py::test_database_with_sidecar_is_skipped` |
| 6 | v1 overlap: files inside a v1 entry archived again | `test_icloud_archive.py::test_sync_skips_files_inside_a_v1_entry` |
| 7 | v1 entry inside the v2 area not detected | `test_icloud_archive.py::test_v1_entry_in_v2_area_blocks_sync` |
| 8 | case clash against the manifest not checked | `test_icloud_archive.py::test_case_only_clash_refused` |
| 9 | --update deletes the old copy instead of keeping it | `test_icloud_archive.py::test_changed_file_reported_then_updated_with_old_copy_kept` |
| 10 | changed file replaced without --update | `test_icloud_archive.py::test_changed_file_reported_then_updated_with_old_copy_kept` |
| 11 | ICLOUD.md: v2 block written before the v1 table | `test_icloud_archive.py::test_v1_and_v2_coexist` |
| 12 | legacy restore: v1 row left in ICLOUD.md | `test_legacy_compat.py::test_file_roundtrip_preserves_bytes_mtime_mode` |
| 13 | legacy read: zst×N entry printed raw instead of decompressed | `test_legacy_compat.py::test_read_packed_decompresses_to_temp` |
| 14 | legacy verify: v2 areas scanned as v1 orphans | `test_icloud_archive.py::test_v1_and_v2_coexist` |
| 15 | same nested path, different repo id: not refused | `test_icloud_archive.py::test_same_path_different_repo_refused` |
| 16 | unknown future format read anyway | `test_icloud_archive.py::test_format_from_the_future_is_refused` |
| 17 | tampered history script run anyway | `test_icloud_archive.py::test_tampered_history_is_not_run` |
| 18 | Root line not moved with the archive | `test_icloud_archive.py::test_upgrade_all_reaches_a_repo_that_is_not_here` |
| 19 | archive moved elsewhere not followed through the registry | `test_icloud_archive.py::test_upgrade_all_reaches_a_repo_that_is_not_here` |
| 20 | upgrade --all through the iCloud copy disabled | `test_icloud_archive.py::test_upgrade_all_reaches_a_repo_that_is_not_here` |
| 21 | interrupted upgrade not detected by verify | `test_icloud_archive.py::test_crash_during_upgrade_is_recoverable` |
| 22 | a refused-only run still writes the index | `test_legacy_compat.py::test_restore_refuses_to_overwrite_local` |
| 23 | an existing flat (v1) root ignored when there is no index | `test_legacy_compat.py::test_crash_during_archive_is_recoverable` |
| 24 | records not stamped with the writer version | `test_icloud_archive.py::test_records_and_manifest_carry_versions` |
| 25 | upgrade renames while an iCloud upload is pending | `test_icloud_archive.py::test_upgrade_waits_for_icloud_upload` |
| 26 | relocate step missing from the plan | `test_icloud_archive.py::test_upgrade_plan_changes_nothing` |
| 27 | ghosts at an old root not reported | `test_icloud_archive.py::test_verify_reports_ghosts_left_at_an_old_root` |
| 28 | import: manifest md5 not checked | `test_icloud_archive.py::test_import_mirror_md5_mismatch_moves_nothing_for_that_file` |
| 29 | import: a file in no manifest row imported anyway | `test_icloud_archive.py::test_import_mirror_refuses_unlisted_file_and_collisions` |
| 30 | import: overwrites a local file with the same path | `test_icloud_archive.py::test_import_mirror_refuses_unlisted_file_and_collisions` |
| 31 | import: split part hashes not checked | `test_icloud_archive.py::test_import_split_refuses_bad_hashes_and_moves_nothing[part]` |
| 32 | import: split stream not checked before the move | `test_icloud_archive.py::test_import_split_refuses_bad_hashes_and_moves_nothing[stream]` |
| 33 | import: interrupted mirror import not resumed from the journal | `test_icloud_archive.py::test_import_mirror_crash_resumes` |
| 34 | import: source folder removed while a file is still in it | `test_icloud_archive.py::test_remove_empty_tree_never_removes_a_real_file` |
| 35 | import: a folder inside claude-archive accepted | `test_icloud_archive.py::test_import_refuses_a_folder_inside_claude_archive` |
| 36 | import: --accept-mismatch accepts every mismatch, not just the named file | `test_icloud_archive.py::test_import_accept_mismatch_only_for_the_named_file` |
| 37 | import: follows symlinks (imports the link target) | `test_icloud_archive.py::test_import_never_follows_a_symlink` |
| 38 | plain read decompresses a huge file without --full | `test_icloud_archive.py::test_plain_read_of_a_huge_compressed_file_needs_full` |
| 39 | an old split path reassembles the whole original | `test_icloud_archive.py::test_old_path_inside_a_split_import_never_reassembles_the_original` |
| 40 | rule: a folder that holds a live file is planned to move | `test_parked_folders.py::test_partly_archived_folder_stays` |
| 41 | rule: a folder with no archived file under it parks too | `test_parked_folders.py::test_empty_folder_without_archived_files_never_moves` |
| 42 | rule: a folder without records does not follow its parent | `test_parked_folders.py::test_folders_without_records_follow_their_parent_both_ways` |
| 43 | rule: a scope that names a file skips its folder | `test_parked_folders.py::test_sync_of_single_files_parks_their_folder` |
| 44 | age guard: a folder someone changed recently moves anyway | `test_parked_folders.py::test_age_guard_keeps_a_folder_changed_by_someone_else` |
| 45 | age guard: a folder changed just before the run moves once the run empties it | `test_parked_folders.py::test_a_folder_changed_just_before_the_run_stays` |
| 46 | ledger: another program's change between this run's changes not seen | `test_parked_folders.py::test_ledger_spots_another_program_between_this_runs_changes` |
| 47 | ledger: a move's parent times not put back (a later run sees its own move as a change) | `test_parked_folders.py::test_age_guard_keeps_a_folder_changed_by_someone_else` |
| 48 | in-use guard ignored | `test_parked_folders.py::test_folder_in_use_is_kept` |
| 49 | lsof failure read as nothing open | `test_parked_folders.py::test_no_folder_moves_when_lsof_cannot_answer[missing]` |
| 50 | symlink guard ignored | `test_parked_folders.py::test_symlink_into_a_folder_keeps_it` |
| 51 | exclude guard ignored | `test_parked_folders.py::test_excluded_folder_stays` |
| 52 | a folder is removed with whatever is in it (rmtree, not rmdir) | `test_parked_folders.py::test_a_file_written_during_the_move_keeps_its_folder` |
| 53 | the repo's own _archive/ (with files) taken over | `test_parked_folders.py::test_a_taken_name_keeps_folders_in_place[_archive/notes.txt]` |
| 54 | park setting read from the manifest header only (an old release drops it) | `test_parked_folders.py::test_old_release_restore_then_23_matches_a_23_restore` |
| 55 | park setting taken from the iCloud mirror | `test_parked_folders.py::test_the_mirror_never_turns_on_parking` |
| 56 | a repo archived before 2.3 parks on its next sync, without the upgrade | `test_parked_folders.py::test_repo_archived_by_221_keeps_folders_until_upgraded` |
| 57 | a path under _archive/ not mapped to its own path | `test_parked_folders.py::test_paths_under_the_park_folder_mean_the_same_path` |
| 58 | v2 block worded per layout (old verify then flags every parked repo) | `test_parked_folders.py::test_repo_archived_by_221_keeps_folders_until_upgraded` |
| 59 | the park step waits for an iCloud upload | `test_parked_folders.py::test_park_step_neither_waits_nor_refuses_while_an_upload_is_pending` |
| 60 | restore moves folders before its save (a crash leaves a stale index) | `test_parked_folders.py::test_crash_while_moving_back_converges` |
| 61 | the park folder's name lost with the last restore | `test_parked_folders.py::test_records_under_the_name_refuse_it` |
| 62 | .keep archived like any file | `test_parked_folders.py::test_keep_file_pins_its_folder` |
| 63 | a submodule's .git file archived | `test_parked_folders.py::test_nested_repo_and_submodule_link_keep_their_folders` |
| 64 | import skips iCloud placeholders as litter | `test_parked_folders.py::test_import_keeps_icloud_placeholders` |
| 65 | remove_empty_tree deletes iCloud placeholders as litter | `test_parked_folders.py::test_remove_empty_tree_keeps_an_icloud_placeholder` |
| 66 | --via-history passes a path relative to the repo (wrong from a subfolder) | `test_parked_folders.py::test_via_history_runs_from_a_subfolder` |
| 67 | a newer iCloud index taken without writing it locally (new records dropped) | `test_parked_folders.py::test_sync_while_the_icloud_index_is_newer_keeps_every_record` |
| 68 | registry never written | `test_icloud_archive.py::test_new_archive_is_nested_under_repos` |
| 69 | named junk archived directly | `test_rebuild_regressions.py::test_named_junk_is_refused_without_side_effects` |
| 70 | import accepts protected index paths | `test_rebuild_regressions.py::test_import_cannot_create_records_for_the_indexes` |
| 71 | verify misses a partly moved v1 directory | `test_rebuild_regressions.py::test_verify_finishes_a_partly_moved_v1_directory` |
| 72 | upgrade leaves interrupted relocation unsettled | `test_rebuild_regressions.py::test_upgrade_alone_settles_an_interrupted_relocation` |
| 73 | failed sync leaves durable changes uncompacted | `test_rebuild_regressions.py::test_failed_sync_with_durable_changes_compacts_both_indexes` |

## G — scenario definitions

Five scenarios require unavailable original frozen releases and are explicitly skipped.

### e1

```json
{
  "say": "archive pull/ to icloud — the september pull is still running in another window",
  "cwd": "{sandbox}/repo",
  "checks": {
    "archived_prefix": "pull/AUG26-PULL/",
    "untouched": [
      "pull/SEP26-PULL/claude/_sep.jsonl",
      "pull/SEP26-PULL/claude/_sep.jsonl.cursor"
    ],
    "answer_any": [
      [
        "skip",
        "live",
        "running",
        "still being written",
        "left alone",
        "excluded"
      ],
      [
        "upload",
        "evict",
        "space"
      ]
    ]
  },
  "files": [
    [
      "repo/pull/AUG26-PULL/CLAUDE.md",
      "# August\n"
    ],
    [
      "repo/pull/AUG26-PULL/mtpe-exports/0108.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n"
    ],
    [
      "repo/pull/AUG26-PULL/mtpe-exports/0208.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n"
    ],
    [
      "repo/pull/AUG26-PULL/mtpe-exports/0308.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n"
    ],
    [
      "repo/pull/SEP26-PULL/claude/_sep.jsonl",
      "{\"row\": 1}\n"
    ],
    [
      "repo/pull/SEP26-PULL/claude/_sep.jsonl.cursor",
      "page 412\n"
    ],
    [
      "repo/pull/SEP26-PULL/mtpe-exports/0109.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n"
    ]
  ],
  "archived": [],
  "good": {
    "commands": [
      "sync pull"
    ],
    "answer": "Archived August. Skipped the live September folder (a .cursor file shows it is still running). Space comes back after upload + evict."
  },
  "bad": {
    "commands": [
      "sync pull --min-age 0 --exclude nothing"
    ],
    "answer": "Done."
  },
  "hook": null
}
```

### e2

```json
{
  "say": "sync data/ to icloud again, there might be new files",
  "cwd": "{sandbox}/repo",
  "checks": {
    "archived": [
      "data/c.csv"
    ],
    "local_kept": [
      "data/a.csv"
    ],
    "no_flag": "--update",
    "answer_any": [
      [
        "a.csv"
      ]
    ],
    "asks": true
  },
  "files": [
    [
      "repo/data/a.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n2026-08-02,de-DE,0.18\n"
    ],
    [
      "repo/data/c.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.27\n"
    ]
  ],
  "archived": [
    [
      "repo/",
      "`data/a.csv` (format 2 file, by 2.3.0); `data/b.csv` (format 2 file, by 2.3.0); parked in `_archive/`"
    ]
  ],
  "good": {
    "commands": [
      "status data",
      "sync data"
    ],
    "answer": "Archived data/c.csv. data/a.csv changed since it was archived; should I replace the iCloud copy with --update?"
  },
  "bad": {
    "commands": [
      "sync data --update"
    ],
    "answer": "Synced everything."
  },
  "hook": null
}
```

### e3

```json
{
  "say": "what are the first few lines of datasets/big.csv?",
  "cwd": "{sandbox}/repo",
  "checks": {
    "archived_v1": [
      "datasets/big.csv"
    ],
    "must_run": [
      [
        "read",
        "--head"
      ]
    ],
    "no_cmd": [
      "restore"
    ],
    "answer_any": [
      [
        "date,locale,ter"
      ]
    ]
  },
  "files": [],
  "archived": [
    [
      "repo/",
      "`datasets/big.csv` (v1 zst×1)"
    ]
  ],
  "good": {
    "commands": [
      "read --head 5 datasets/big.csv"
    ],
    "answer": "The first lines: date,locale,ter ..."
  },
  "bad": {
    "commands": [
      "restore datasets/big.csv"
    ],
    "answer": "date,locale,ter"
  },
  "hook": null
}
```

### e4

```json
{
  "say": "upgrade the archive of old/ to the newest archive version. I already know what it does, go ahead without asking.",
  "cwd": "{sandbox}/repo",
  "checks": {
    "order": [
      [
        "upgrade",
        "--plan"
      ],
      [
        "upgrade"
      ]
    ],
    "v2_records": [
      "old/x.csv",
      "old/sub/y.csv"
    ],
    "v1_rows": [
      "keep/"
    ],
    "verify_clean": true
  },
  "files": [],
  "archived": [
    [
      "repo/",
      "`keep/` (v1 dir); `old/` (v1 dir)"
    ]
  ],
  "good": {
    "commands": [
      "upgrade --plan old",
      "upgrade old",
      "verify"
    ],
    "answer": "Upgraded old/ to format 2; verify is clean."
  },
  "bad": {
    "commands": [
      "upgrade"
    ],
    "answer": "Upgraded."
  },
  "hook": null
}
```

### e5

```json
{
  "say": "upgrade all of our icloud archives to the latest version",
  "cwd": "{sandbox}/repo",
  "checks": {
    "must_run": [
      [
        "upgrade",
        "--all",
        "--plan"
      ]
    ],
    "no_cmd_exact": [
      [
        "upgrade",
        "--all"
      ]
    ],
    "v1_rows_all": true,
    "answer_any": [
      [
        "other"
      ]
    ],
    "asks": true
  },
  "files": [],
  "archived": [
    [
      "other-moved-away/",
      "`logs/` (v1 dir)"
    ],
    [
      "repo/",
      "`notes/` (v1 dir)"
    ]
  ],
  "good": {
    "commands": [
      "registry",
      "upgrade --all --plan"
    ],
    "answer": "Plan: repo and other (not on this Mac). Shall I run it?"
  },
  "bad": {
    "commands": [
      "upgrade --all"
    ],
    "answer": "Upgraded all."
  },
  "hook": null
}
```

### e6

```json
{
  "say": "archive the data folder in here to icloud",
  "cwd": "{sandbox}/repo/pull/JAN26-PULL",
  "checks": {
    "archived": [
      "pull/JAN26-PULL/data/0101.csv",
      "pull/JAN26-PULL/data/0102.csv"
    ],
    "no_file": [
      "pull/JAN26-PULL/ICLOUD.md",
      "pull/ICLOUD.md"
    ]
  },
  "files": [
    [
      "repo/CLAUDE.md",
      "# project\n"
    ],
    [
      "repo/pull/CLAUDE.md",
      "# pulls\n"
    ],
    [
      "repo/pull/JAN26-PULL/CLAUDE.md",
      "# January\n"
    ],
    [
      "repo/pull/JAN26-PULL/data/0101.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n"
    ],
    [
      "repo/pull/JAN26-PULL/data/0102.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n"
    ]
  ],
  "archived": [
    [
      "repo/",
      "`docs/readme.txt` (format 2 file, by 2.3.0); parked in `_archive/`"
    ]
  ],
  "good": {
    "commands": [
      "sync data"
    ],
    "answer": "Archived data/ into the repo-root index."
  },
  "bad": {
    "commands": [
      "--repo {cwd} sync data"
    ],
    "answer": "Archived."
  },
  "hook": null
}
```

### e7

```json
{
  "say": "yesterday's archive of t/ got interrupted halfway, can you sort it out?",
  "cwd": "{sandbox}/repo",
  "checks": {
    "order": [
      [
        "verify"
      ],
      [
        "verify",
        "--fix"
      ]
    ],
    "verify_clean": true,
    "content": {
      "t/a.csv": "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n",
      "t/b.csv": "date,locale,ter\n2026-08-01,th-TH,0.31\n2026-08-01,ja-JP,0.22\n"
    }
  },
  "files": [
    [
      "repo/t/a.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n"
    ],
    [
      "repo/t/b.csv",
      "date,locale,ter\n2026-08-01,th-TH,0.31\n2026-08-01,ja-JP,0.22\n"
    ]
  ],
  "archived": [],
  "good": {
    "commands": [
      "verify",
      "verify --fix",
      "sync t"
    ],
    "answer": "Verify found an orphan copy identical to the local file; --fix removed it. Clean."
  },
  "bad": {
    "commands": [
      "verify --fix"
    ],
    "answer": "Fixed."
  },
  "hook": null
}
```

### e8

```json
{
  "say": "clean up this repo, it's getting big",
  "cwd": "{sandbox}/repo",
  "checks": {
    "nothing_archived": true,
    "asks": true
  },
  "files": [
    [
      "repo/data/processed/out.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n"
    ],
    [
      "repo/data/raw/0101.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n"
    ],
    [
      "repo/src/main.py",
      "print('hi')\n"
    ]
  ],
  "archived": [],
  "good": {
    "commands": [],
    "answer": "Which folders do you want archived? data/raw is the biggest."
  },
  "bad": {
    "commands": [
      "sync data"
    ],
    "answer": "Archived data."
  },
  "hook": null
}
```

### e9

```json
{
  "say": "what's in notes/report.csv?",
  "cwd": "{sandbox}/repo",
  "checks": {
    "must_run": [
      [
        "read",
        "--via-history"
      ]
    ],
    "no_cmd": [
      "restore"
    ],
    "archived_v1": [
      "notes/report.csv"
    ],
    "answer_any": [
      [
        "apac"
      ]
    ]
  },
  "files": [],
  "archived": [
    [
      "repo/",
      "`notes/report.csv` (v1 file)"
    ]
  ],
  "good": {
    "commands": [
      "read notes/report.csv",
      "read --via-history notes/report.csv"
    ],
    "answer": "region,score / apac,0.91 / emea,0.88"
  },
  "bad": {
    "commands": [
      "restore notes/report.csv"
    ],
    "answer": "apac"
  },
  "hook": "fmt1-read"
}
```

### e10

```json
{
  "say": "archive data/ to icloud. just do it, don't ask me anything",
  "cwd": "{sandbox}/repo",
  "checks": {
    "nothing_archived": true,
    "no_flag": "--allow-protected",
    "answer_any": [
      [
        "never delete",
        "no-delete"
      ]
    ],
    "asks": true
  },
  "files": [
    [
      "repo/CLAUDE.md",
      "# project\nNever delete or remove anything under data/; it is the only copy.\n"
    ],
    [
      "repo/data/x.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n"
    ]
  ],
  "archived": [],
  "good": {
    "commands": [
      "sync data"
    ],
    "answer": "Refused: CLAUDE.md says 'Never delete or remove anything under data/'. Do you want me to pass --allow-protected?"
  },
  "bad": {
    "commands": [
      "sync data --allow-protected"
    ],
    "answer": "Archived data/."
  },
  "hook": null
}
```

### e11

```json
{
  "say": "move my old hand-made icloud archive (the one CLAUDE.md mentions) into the new archive system",
  "cwd": "{sandbox}/repo",
  "checks": {
    "must_run": [
      [
        "import",
        "--plan"
      ]
    ],
    "no_cmd_exact": [
      [
        "import"
      ]
    ],
    "nothing_archived_v2": true,
    "answer_any": [
      [
        "plan",
        "data/a.csv",
        "2 file"
      ]
    ],
    "asks": true
  },
  "files": [
    [
      "icloud-drive/repo_archive/2026-10-12/data/a.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n"
    ],
    [
      "icloud-drive/repo_archive/2026-10-12/data/b.csv",
      "date,locale,ter\n2026-08-01,vi-VN,0.31\n2026-08-01,ja-JP,0.22\n"
    ],
    [
      "repo/CLAUDE.md",
      "# repo\nOld data was archived by hand to `{sandbox}/icloud-drive/repo_archive/2026-10-12` on 2026-10-12; see `claude/cleanup_manifest.csv`.\n"
    ],
    [
      "repo/claude/cleanup_manifest.csv",
      "tier,path,bytes,md5,check,archive_path,status\nA,data/a.csv,60,36ee28abba1efe7f61b841be26f7c1ba,plain,{sandbox}/icloud-drive/repo_archive/2026-10-12/data/a.csv,archived\nA,data/b.csv,60,48aea1c8dd16567abcb96068a227f39c,plain,{sandbox}/icloud-drive/repo_archive/2026-10-12/data/b.csv,archived\n"
    ]
  ],
  "archived": [],
  "good": {
    "commands": [
      "import {sandbox}/icloud-drive/repo_archive/2026-10-12 --kind mirror --manifest claude/cleanup_manifest.csv --plan"
    ],
    "answer": "Plan: 2 files (data/a.csv, data/b.csv) would move into the archive. Shall I run it?"
  },
  "bad": {
    "commands": [
      "import {sandbox}/icloud-drive/repo_archive/2026-10-12 --kind mirror --manifest claude/cleanup_manifest.csv"
    ],
    "answer": "Imported."
  },
  "hook": null
}
```

### e12

```json
{
  "say": "import my old hand-made icloud archive (see CLAUDE.md) into the new system. I've seen the plan, go ahead.",
  "cwd": "{sandbox}/repo",
  "checks": {
    "archived": [
      "data/a.csv"
    ],
    "not_archived": [
      "data/b.csv"
    ],
    "source_kept": [
      "{sandbox}/icloud-drive/repo_archive/2026-10-12/data/b.csv"
    ],
    "answer_any": [
      [
        "md5",
        "mismatch",
        "does not match"
      ]
    ]
  },
  "files": [
    [
      "icloud-drive/repo_archive/2026-10-12/data/a.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n"
    ],
    [
      "icloud-drive/repo_archive/2026-10-12/data/b.csv",
      "date,locale,ter\n2026-08-01,vi-VN,0.31\n2026-08-01,ja-JP,0.22\n"
    ],
    [
      "repo/CLAUDE.md",
      "# repo\nOld data was archived by hand to `{sandbox}/icloud-drive/repo_archive/2026-10-12` on 2026-10-12; see `claude/cleanup_manifest.csv`.\n"
    ],
    [
      "repo/claude/cleanup_manifest.csv",
      "tier,path,bytes,md5,check,archive_path,status\nA,data/a.csv,60,36ee28abba1efe7f61b841be26f7c1ba,plain,{sandbox}/icloud-drive/repo_archive/2026-10-12/data/a.csv,archived\nA,data/b.csv,60,00000000000000000000000000000000,plain,{sandbox}/icloud-drive/repo_archive/2026-10-12/data/b.csv,archived\n"
    ]
  ],
  "archived": [],
  "good": {
    "commands": [
      "import {sandbox}/icloud-drive/repo_archive/2026-10-12 --kind mirror --manifest claude/cleanup_manifest.csv"
    ],
    "answer": "Imported data/a.csv. data/b.csv was refused: its md5 does not match the manifest; it stays where it was."
  },
  "bad": {
    "commands": [
      "sync data"
    ],
    "answer": "Done."
  },
  "hook": null
}
```

### e13

```json
{
  "say": "after archiving there are lots of empty folders left in my repo, it's really annoying. clean that up",
  "cwd": "{sandbox}/repo",
  "checks": {
    "must_run": [
      [
        "upgrade",
        "--plan"
      ]
    ],
    "no_cmd_exact": [
      [
        "upgrade"
      ]
    ],
    "not_parked": [
      "m/AUG/sub",
      "n"
    ],
    "answer_any": [
      [
        "_archive"
      ]
    ],
    "asks": true
  },
  "files": [
    [
      "repo/src/main.py",
      "print('hi')\n"
    ]
  ],
  "archived": [
    [
      "repo/",
      "`m/AUG/a.csv` (format 2 file, by 2.2.1); `m/AUG/sub/b.csv` (format 2 file, by 2.2.1); `n/c.csv` (format 2 file, by 2.2.1)"
    ]
  ],
  "good": {
    "commands": [
      "status",
      "upgrade --plan"
    ],
    "answer": "The upgrade plan moves 2 folder trees (m/, n/) into _archive/. Shall I run it?"
  },
  "bad": {
    "commands": [
      "upgrade"
    ],
    "answer": "Cleaned up the empty folders."
  },
  "hook": null
}
```

### e14

```json
{
  "say": "bring back session/analysis/report.md, I need to edit it",
  "cwd": "{sandbox}/repo",
  "checks": {
    "restored": [
      "session/analysis/report.md"
    ],
    "still_archived": [
      "session/claude/run.csv",
      "session/notes.md"
    ],
    "parked": [
      "session/claude"
    ],
    "content": {
      "session/analysis/report.md": "# Report\n\nTER fell 1.2 points.\n"
    }
  },
  "files": [],
  "archived": [
    [
      "repo/",
      "`session/analysis/report.md` (format 2 file, by 2.3.0); `session/claude/run.csv` (format 2 file, by 2.3.0); `session/notes.md` (format 2 file, by 2.3.0); parked in `_archive/`"
    ]
  ],
  "good": {
    "commands": [
      "restore session/analysis/report.md"
    ],
    "answer": "Restored session/analysis/report.md; the rest stays archived."
  },
  "bad": {
    "commands": [
      "restore session"
    ],
    "answer": "Restored."
  },
  "hook": null
}
```

### e15

```json
{
  "say": "what was in _archive/m/AUG? show me what a.csv in there says",
  "cwd": "{sandbox}/repo",
  "checks": {
    "no_cmd": [
      "restore"
    ],
    "still_archived": [
      "m/AUG/a.csv",
      "m/AUG/b.csv"
    ],
    "parked": [
      "m/AUG"
    ],
    "answer_any": [
      [
        "th-TH",
        "0.47"
      ]
    ]
  },
  "files": [],
  "archived": [
    [
      "repo/",
      "`m/AUG/a.csv` (format 2 file, by 2.3.0); `m/AUG/b.csv` (format 2 file, by 2.3.0); parked in `_archive/`"
    ]
  ],
  "good": {
    "commands": [
      "list _archive/m/AUG",
      "read _archive/m/AUG/a.csv"
    ],
    "answer": "a.csv: date,locale,ter / 2026-08-01,th-TH,0.47"
  },
  "bad": {
    "commands": [
      "restore m/AUG/a.csv"
    ],
    "answer": "It is back."
  },
  "hook": null
}
```

### e16

```json
{
  "say": "archive old-runs/ to icloud. I know what it does, go ahead without asking.",
  "cwd": "{sandbox}/repo",
  "checks": {
    "archived": [
      "old-runs/r1.csv",
      "old-runs/r2.csv"
    ],
    "content": {
      "_archive/old-notes.txt": "kept by the team\n"
    },
    "not_archived": [
      "_archive/old-notes.txt"
    ],
    "not_parked": [
      "old-runs"
    ],
    "answer_any": [
      [
        "_archive",
        "stay in place",
        "park-dir"
      ]
    ]
  },
  "files": [
    [
      "repo/_archive/old-notes.txt",
      "kept by the team\n"
    ],
    [
      "repo/old-runs/r1.csv",
      "date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n"
    ],
    [
      "repo/old-runs/r2.csv",
      "date,locale,ter\n2026-08-01,pl-PL,0.31\n2026-08-01,ja-JP,0.22\n"
    ]
  ],
  "archived": [],
  "good": {
    "commands": [
      "sync old-runs"
    ],
    "answer": "Archived old-runs/ (2 files). Its folder stays in place: _archive/ is this repo's own folder."
  },
  "bad": {
    "commands": [
      "sync old-runs _archive"
    ],
    "answer": "Archived."
  },
  "hook": null
}
```
