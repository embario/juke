from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


CANONICAL_ITEM_NAMESPACE = uuid.UUID('9f291c3d-bb5c-4fd7-a1cd-730f4f9dc9b7')


def _canonical_identity_for_track(track) -> tuple[str, str, uuid.UUID]:
    if track.mbid is not None:
        item_type = 'recording_mbid'
        key_value = str(track.mbid)
    elif getattr(track, 'spotify_id', ''):
        item_type = 'spotify_track'
        key_value = str(track.spotify_id)
    else:
        item_type = 'catalog_track'
        key_value = str(track.juke_id)

    canonical_key = f'{item_type}:{key_value}'
    item_id = uuid.uuid5(CANONICAL_ITEM_NAMESPACE, canonical_key)
    return item_type, canonical_key, item_id


def forwards(apps, schema_editor):
    CanonicalItem = apps.get_model('mlcore', 'CanonicalItem')
    EventLedger = apps.get_model('mlcore', 'ListenBrainzEventLedger')
    SessionTrack = apps.get_model('mlcore', 'ListenBrainzSessionTrack')
    Track = apps.get_model('catalog', 'Track')

    track_map: dict[uuid.UUID, CanonicalItem] = {}
    for track in Track.objects.filter(
        models.Q(listenbrainz_event_ledgers__isnull=False)
        | models.Q(listenbrainz_session_tracks__isnull=False)
    ).distinct():
        item_type, canonical_key, item_id = _canonical_identity_for_track(track)
        canonical_item, _ = CanonicalItem.objects.get_or_create(
            canonical_key=canonical_key,
            defaults={
                'id': item_id,
                'item_type': item_type,
                'track_id': track.juke_id,
            },
        )
        if canonical_item.track_id is None:
            canonical_item.track_id = track.juke_id
            canonical_item.save(update_fields=['track'])
        track_map[track.juke_id] = canonical_item

    for row in EventLedger.objects.filter(track_id__isnull=False):
        canonical_item = track_map.get(row.track_id)
        if canonical_item is not None:
            row.canonical_item_id = canonical_item.pk
            row.save(update_fields=['canonical_item'])

    for row in SessionTrack.objects.filter(track_id__isnull=False):
        canonical_item = track_map.get(row.track_id)
        if canonical_item is not None:
            row.canonical_item_id = canonical_item.pk
            row.save(update_fields=['canonical_item'])


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_albumexternalidentifier_artistexternalidentifier_and_more'),
        ('mlcore', '0011_fullingestionlease'),
    ]

    operations = [
        migrations.CreateModel(
            name='CanonicalItem',
            fields=[
                ('id', models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ('item_type', models.CharField(choices=[('recording_mbid', 'Recording MBID'), ('spotify_track', 'Spotify Track'), ('recording_msid', 'Recording MSID'), ('catalog_track', 'Catalog Track')], max_length=32)),
                ('canonical_key', models.CharField(max_length=512, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('track', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='canonical_items', to='catalog.track', to_field='juke_id')),
            ],
            options={
                'db_table': 'mlcore_canonical_item',
                'ordering': ['item_type', 'canonical_key'],
            },
        ),
        migrations.AddIndex(
            model_name='canonicalitem',
            index=models.Index(fields=['item_type'], name='mlcore_ci_item_ty_ef87b5_idx'),
        ),
        migrations.AddIndex(
            model_name='canonicalitem',
            index=models.Index(fields=['track'], name='mlcore_ci_track_i_79f9ca_idx'),
        ),
        migrations.AddField(
            model_name='listenbrainzeventledger',
            name='canonical_item',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='listenbrainz_event_ledgers', to='mlcore.canonicalitem'),
        ),
        migrations.AddField(
            model_name='listenbrainzsessiontrack',
            name='canonical_item',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='listenbrainz_session_tracks', to='mlcore.canonicalitem'),
        ),
        migrations.AlterField(
            model_name='listenbrainzsessiontrack',
            name='track',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='listenbrainz_session_tracks', to='catalog.track', to_field='juke_id'),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='listenbrainzsessiontrack',
            name='canonical_item',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='listenbrainz_session_tracks', to='mlcore.canonicalitem'),
        ),
        migrations.AlterUniqueTogether(
            name='listenbrainzsessiontrack',
            unique_together={('session_key', 'canonical_item')},
        ),
        migrations.AddIndex(
            model_name='listenbrainzeventledger',
            index=models.Index(fields=['canonical_item'], name='mlcore_lbe_canonic_9067f9_idx'),
        ),
        migrations.AddIndex(
            model_name='listenbrainzsessiontrack',
            index=models.Index(fields=['canonical_item'], name='mlcore_lst_canonic_78087f_idx'),
        ),
    ]
