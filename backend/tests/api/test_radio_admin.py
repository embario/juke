from django.test import TestCase
from django.urls import reverse

from juke_auth.models import JukeUser
from radio.models import Exclusion, Station


class StationExclusionAdminTests(TestCase):
    def setUp(self):
        self.owner = JukeUser.objects.create_user(username='listener')
        self.operator = JukeUser.objects.create_superuser(username='operator', email='admin@example.com', password='test')
        self.client.force_login(self.operator)
        self.station = Station.objects.create(user=self.owner, name='Station', frequency='95.1')
        self.url = reverse('admin:radio_station_change', args=[self.station.pk])

    def save_exclusion(self, scope):
        return self.client.post(self.url, {
            'user': self.owner.pk, 'name': self.station.name, 'kind': self.station.kind,
            'frequency': '95.1', 'seeds': '[]', 'feelings': '[]', 'learning': 'on',
            'exclusions-TOTAL_FORMS': '1', 'exclusions-INITIAL_FORMS': '0',
            'exclusions-MIN_NUM_FORMS': '0', 'exclusions-MAX_NUM_FORMS': '1000',
            'exclusions-0-scope': scope, 'exclusions-0-kind': 'artist',
            'exclusions-0-value': 'artist-id', 'exclusions-0-label': 'Artist',
            '_save': 'Save',
        })

    def test_inline_assigns_station_owner(self):
        self.assertEqual(self.save_exclusion('station').status_code, 302)
        exclusion = Exclusion.objects.get()
        self.assertEqual(exclusion.user, self.owner)
        self.assertEqual(exclusion.station, self.station)

    def test_everywhere_inline_has_no_station(self):
        self.assertEqual(self.save_exclusion('everywhere').status_code, 302)
        exclusion = Exclusion.objects.get()
        self.assertEqual(exclusion.user, self.owner)
        self.assertIsNone(exclusion.station)
