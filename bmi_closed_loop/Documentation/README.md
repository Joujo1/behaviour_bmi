# Documentation

## Architecture & Diagrams
- [System Overview](architecture/01_system_overview.md)
- [UDP Data Flow](architecture/02_udp_data_flow.md)
- [Trial Events & Database Flow](architecture/03_trial_events_database_flow.md)
- [Valkey Architecture](architecture/04_valkey_architecture.md)
- [Trial State Machine (Pi)](architecture/05_trial_state_machine.md)
- [Cage Runner Flowchart](architecture/06_cage_runner_flowchart.md)
- [Clocks & Timestamping Policy](architecture/07_clocks_and_timestamping.md)
- [Database Schema](architecture/08_database_schema.md)

## Reference
- [Trial JSON Document](reference/01_trial_json.md)
- [UDP Packet Format](reference/02_udp_packet_format.md)
- [TCP Commands](reference/03_tcp_commands.md)
- [Bias Algorithms](reference/04_bias_algorithms.md)
- [Config Files](reference/05_config_files.md)
- [Systemd Services on Pi](reference/06_systemd_services.md)
- [Logs](reference/07_logs.md)

## Hardware & Setup
- [Wiring and Setting Up All Hardware](setup/01_hardware_wiring.md)
- [Setting Up New Pis](setup/02_setting_up_pis.md)
- [Wiring the NAS](setup/03_wiring_the_nas.md)
- [Connecting New ItsyBitsy MCU](setup/04_itsybitsy_mcu.md)
- [Network Setup](setup/05_network_setup.md)
- [Camera Setup](setup/06_camera_setup.md)

## Operations
- [A First Session in 20 Min](operations/01_first_session.md)
- [Daily Workflow](operations/02_daily_workflow.md)
- [Daily Welfare Scoresheet Handling](operations/03_welfare_scoresheet.md)
- [Dashboard, Curriculum & Subjects Page Walkthrough](operations/04_ui_pages_walkthrough.md)
- [How Click Rates Are Calculated](operations/05_click_rates.md)
- [Reading Per-Frame Packages from NAS](operations/06_reading_per_frame_packages.md)
- [How to Read Trial Events](operations/07_reading_trial_events.md)
- [Regenerating a Stimulus](operations/08_regenerating_stimulus.md)

## Troubleshooting
- [Camera Failures](troubleshooting/01_camera_failures.md)
- [Pi Disconnects & Reconnection](troubleshooting/02_pi_disconnects.md)
- [Valkey Unreachable or Stale Keys](troubleshooting/03_valkey_issues.md)
- [NAS Mount Failures](troubleshooting/04_nas_mount_failures.md)
- [Click Detection Dropout](troubleshooting/05_click_detection_dropout.md)
- [General Debugging: Logs & Systemd](troubleshooting/06_general_debugging.md)

## Extending the System
- [Adding Cages to the Dashboard](extending/01_adding_cages.md)
- [Adding and Changing the Database Schema](extending/02_database_schema.md)
- [Adding Export Options](extending/03_export_options.md)
- [Adding Side Bias Algorithms](extending/04_bias_algorithms.md)
- [Adding Actions](extending/05_actions.md)
- [Adding Events to UDP Sender](extending/06_udp_events.md)
- [Changing Resolution](extending/07_resolution.md)
- [Adding Advancement Criteria](extending/08_advancement_criteria.md)
- [Adding Endpoints](extending/09_endpoints.md)
- [Adding UI Buttons and Dropdowns](extending/10_ui_buttons_dropdowns.md)
- [Adding Status Dots on UI](extending/11_status_dots.md)
- [Adding and Changing Subject Definitions](extending/12_subject_definitions.md)
- [Adding Live Metric Plots](extending/13_live_metric_plots.md)
- [Adding and Changing Click Waveform](extending/14_click_waveform.md)
- [Adding TCP Commands](extending/15_tcp_commands.md)
- [Adding Sensors](extending/16_sensors.md)

