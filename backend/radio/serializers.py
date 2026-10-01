"""Request validation for the radio API (camelCase in, camelCase out)."""
from rest_framework import serializers

from radio.models import EXCLUSION_KIND_CHOICES, EXCLUSION_SCOPE_CHOICES, LISTENING_EVENTS

MAX_REACTION_LENGTH = 40
MAX_SEEDS = 20
MAX_FEELINGS = 12


def unique_strings(values, *, max_length, field_name):
    seen, result = set(), []
    for value in values:
        if not isinstance(value, str):
            raise serializers.ValidationError(f'Each {field_name} must be a string.')
        value = value.strip()
        if not value:
            continue
        if len(value) > max_length:
            raise serializers.ValidationError(f'Each {field_name} must be at most {max_length} characters.')
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


class SeedSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=('track', 'artist', 'album'))
    spotifyId = serializers.CharField(max_length=64)
    title = serializers.CharField(max_length=200)
    subtitle = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    artworkUrl = serializers.URLField(max_length=1000, required=False, allow_null=True, allow_blank=True, default=None)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        value['artworkUrl'] = value.get('artworkUrl') or None
        return value


def _unique_seeds(seeds):
    unique = {}
    for seed in seeds:
        unique.setdefault((seed['kind'], seed['spotifyId']), seed)
    return list(unique.values())


class FeelingsField(serializers.ListField):
    child = serializers.CharField(allow_blank=True, trim_whitespace=False)

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        values = unique_strings(values, max_length=MAX_REACTION_LENGTH, field_name='feeling')
        if len(values) > MAX_FEELINGS:
            raise serializers.ValidationError(f'At most {MAX_FEELINGS} feelings.')
        return values


class StationCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    seeds = SeedSerializer(many=True, required=False, default=list)
    feelings = FeelingsField(required=False, default=list)

    def validate_seeds(self, seeds):
        seeds = _unique_seeds(seeds)
        if len(seeds) > MAX_SEEDS:
            raise serializers.ValidationError(f'At most {MAX_SEEDS} seeds.')
        return seeds

    def validate(self, attrs):
        if not attrs.get('seeds') and not attrs.get('feelings'):
            raise serializers.ValidationError('Pick at least one record or feeling.')
        return attrs


class StationUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    frequency = serializers.DecimalField(max_digits=6, decimal_places=3, required=False, coerce_to_string=False)
    seeds = SeedSerializer(many=True, required=False)
    feelings = FeelingsField(required=False)
    learning = serializers.BooleanField(required=False)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Name cannot be blank.')
        return value

    def validate_seeds(self, seeds):
        seeds = _unique_seeds(seeds)
        if len(seeds) > MAX_SEEDS:
            raise serializers.ValidationError(f'At most {MAX_SEEDS} seeds.')
        return seeds


class ExclusionCreateSerializer(serializers.Serializer):
    scope = serializers.ChoiceField(choices=[choice for choice, _ in EXCLUSION_SCOPE_CHOICES])
    kind = serializers.ChoiceField(choices=[choice for choice, _ in EXCLUSION_KIND_CHOICES])
    value = serializers.CharField(max_length=200)
    label = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')


class ReactionsSerializer(serializers.Serializer):
    spotifyTrackId = serializers.CharField(max_length=64)
    stationId = serializers.UUIDField(required=False, allow_null=True)
    reactions = serializers.ListField(child=serializers.CharField(allow_blank=True, trim_whitespace=False), max_length=50)

    def validate_reactions(self, values):
        return unique_strings(values, max_length=MAX_REACTION_LENGTH, field_name='reaction')


class NextSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=1, max_value=10, required=False, default=3)
    recentTrackIds = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list,
                                           max_length=200)


class PlaySerializer(serializers.Serializer):
    stationId = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=('now', 'queue'))
    deviceId = serializers.CharField(max_length=128, required=False, allow_null=True, allow_blank=True)
    recentTrackIds = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list,
                                           max_length=200)


class EventSerializer(serializers.Serializer):
    stationId = serializers.UUIDField(required=False, allow_null=True)
    spotifyTrackId = serializers.CharField(max_length=64)
    event = serializers.ChoiceField(choices=LISTENING_EVENTS)
    positionMs = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    source = serializers.CharField(max_length=32, required=False, allow_blank=True, default='')
    artistId = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')


class CrateQuerySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=('tracks', 'artists', 'albums'), required=False, default='tracks')
    q = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
