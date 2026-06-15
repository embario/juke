import uuid

from django.test import TestCase

from mlcore.models import CanonicalItem, CanonicalItemRedirect
from mlcore.services.canonical_items import identity_from_parts
from mlcore.services.canonical_redirects import resolve_canonical_item_id, upsert_canonical_redirect


class CanonicalRedirectTests(TestCase):

    def _item(self, item_type, value):
        identity = identity_from_parts(item_type=item_type, key_value=value)
        return CanonicalItem.objects.create(
            id=identity.item_id,
            item_type=identity.item_type,
            canonical_key=identity.canonical_key,
        )

    def test_resolves_active_redirect_chain(self):
        source = self._item('recording_msid', uuid.uuid4())
        intermediate = self._item('recording_mbid', uuid.uuid4())
        target = self._item('recording_mbid', uuid.uuid4())
        upsert_canonical_redirect(
            from_item_id=source.id,
            to_item_id=intermediate.id,
            source='test',
            source_version='v1',
        )
        upsert_canonical_redirect(
            from_item_id=intermediate.id,
            to_item_id=target.id,
            source='test',
            source_version='v1',
        )

        self.assertEqual(resolve_canonical_item_id(source.id), target.id)

    def test_unredirected_item_resolves_to_itself(self):
        item = self._item('recording_msid', uuid.uuid4())

        self.assertEqual(resolve_canonical_item_id(item.id), item.id)

    def test_marks_contradictory_target_as_conflict_without_repointing(self):
        source = self._item('recording_msid', uuid.uuid4())
        original = self._item('recording_mbid', uuid.uuid4())
        contradictory = self._item('recording_mbid', uuid.uuid4())
        upsert_canonical_redirect(
            from_item_id=source.id,
            to_item_id=original.id,
            source='test',
            source_version='v1',
        )

        redirect = upsert_canonical_redirect(
            from_item_id=source.id,
            to_item_id=contradictory.id,
            source='test-two',
            source_version='v2',
        )

        self.assertEqual(redirect.status, 'conflict')
        self.assertEqual(redirect.to_canonical_item_id, original.id)
        self.assertEqual(redirect.evidence['conflicting_target_id'], str(contradictory.id))

    def test_rejects_cycle_and_self_redirect(self):
        first = self._item('recording_msid', uuid.uuid4())
        second = self._item('recording_mbid', uuid.uuid4())
        upsert_canonical_redirect(
            from_item_id=first.id,
            to_item_id=second.id,
            source='test',
            source_version='v1',
        )

        with self.assertRaisesRegex(ValueError, 'cycle'):
            upsert_canonical_redirect(
                from_item_id=second.id,
                to_item_id=first.id,
                source='test',
                source_version='v1',
            )
        with self.assertRaisesRegex(ValueError, 'itself'):
            upsert_canonical_redirect(
                from_item_id=first.id,
                to_item_id=first.id,
                source='test',
                source_version='v1',
            )

    def test_redirect_table_is_hot(self):
        self.assertEqual(CanonicalItemRedirect._meta.db_tablespace, 'juke_mlcore_hot')
