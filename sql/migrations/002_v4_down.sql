alter table relay_queue drop column if exists handed_off_at;
alter table relay_queue drop column if exists acked_at;
alter table relay_queue drop column if exists ack_status;
alter table relay_queue drop column if exists make_run_note;
alter table relay_state drop column if exists value;