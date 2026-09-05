-- 0002_storage.sql — private "clips" bucket + owner-only object policies (BLUEPRINT / master prompt Phase 3)
-- Object path: <user_id>/<session_id>/<idx>.wav ; guest clips: guest/<session_id>/<idx>.wav (service role only).
-- The bucket row CONVERGES on the private config on re-run (a dashboard-created public bucket is fixed, not kept).
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('clips', 'clips', false, 26214400, array['audio/wav', 'audio/x-wav', 'audio/wave'])
on conflict (id) do update
  set public = excluded.public, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists clips_select_own on storage.objects;
create policy clips_select_own on storage.objects for select to authenticated
  using (bucket_id = 'clips' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists clips_insert_own on storage.objects;
create policy clips_insert_own on storage.objects for insert to authenticated
  with check (bucket_id = 'clips' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists clips_update_own on storage.objects;
create policy clips_update_own on storage.objects for update to authenticated
  using (bucket_id = 'clips' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'clips' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists clips_delete_own on storage.objects;
create policy clips_delete_own on storage.objects for delete to authenticated
  using (bucket_id = 'clips' and (storage.foldername(name))[1] = (select auth.uid())::text);
