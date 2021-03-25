# -*- coding: utf-8 -*-
from __future__ import division
import datetime, os
from collections import OrderedDict
from django.conf import settings as django_settings
from django.utils.translation import ugettext_lazy as _, string_concat, get_language
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils.safestring import mark_safe
from django.db.models import Q
from django.db.models.fields import BLANK_CHOICE_DASH
from django import forms
from magi.item_model import i_choices
from magi.utils import (
    join_data,
    shrinkImageFromData,
    randomString,
    tourldash,
    PastOnlyValidator,
    getAccountIdsFromSession,
    snakeToCamelCase,
    staticImageURL,
    filterEventsByStatus,
)
from magi.forms import (
    MagiForm,
    AutoForm,
    HiddenModelChoiceField,
    MagiFiltersForm,
    MagiFilter,
    MultiImageField,
    AccountForm as _AccountForm,
    AccountFilterForm as _AccountFilterForm,
    UserFilterForm as _UserFilterForm,
    UserPreferencesForm as _UserPreferencesForm,
)
from magi.middleware.httpredirect import HttpRedirectException
from magi import settings
from bang.django_translated import t
from bang import models

# TODO:
# - Replace member_band utils with merge fields utils: https://github.com/MagiCircles/MagiCircles/wiki/MagiFiltersForm#merge-fields
# - Replace getattr(django_settings, 'FAVORITE_CHARACTERS', []) with getCharactersChoices utils

############################################################
# Form utils

MEMBER_BAND_CHOICE_FIELD = forms.ChoiceField(
    choices=BLANK_CHOICE_DASH + [
        (u'member-{}'.format(id), full_name)
        for (id, full_name, image) in getattr(django_settings, 'FAVORITE_CHARACTERS', [])
    ] + [
        (u'band-{}'.format(i), band)
        for i, band in i_choices(models.Member.BAND_CHOICES)
    ],
    label=string_concat(_('Member'), ' / ', _('Band')),
    initial=None,
)

def member_band_to_queryset(prefix=''):
    def _member_band_to_queryset(form, queryset, request, value):
        if value.startswith('member-'):
            return queryset.filter(**{ u'{}member_id'.format(prefix): value[7:] })
        elif value.startswith('band-'):
            return queryset.filter(**{ u'{}member__i_band'.format(prefix): value[5:] })
        return queryset
    return _member_band_to_queryset

_MEMBERS_CHOICES = [
    (_id, _full_name)
    for (_id, _full_name, _image) in getattr(django_settings, 'FAVORITE_CHARACTERS', [])
]

def memberBandMergeFields(selector_prefix=''):
    return OrderedDict([
        ('member', {
            'label': _('Member'),
            'choices': _MEMBERS_CHOICES,
            'filter': MagiFilter(selector='{}member'.format(selector_prefix)),
        }),
        ('i_band', {
            'label': _('Band'),
            'choices': i_choices(models.AreaItem.BAND_CHOICES),
            'filter': MagiFilter(selector='{}i_band'.format(selector_prefix)),
        }),
    ])

############################################################
# Users

class UserFilterForm(_UserFilterForm):
    favorited_card = forms.IntegerField(widget=forms.HiddenInput)
    favorited_card_filter = MagiFilter(selector='favorite_cards__card_id')

class UserPreferencesForm(_UserPreferencesForm):
    def __init__(self, *args, **kwargs):
        super(UserPreferencesForm, self).__init__(*args, **kwargs)
        if 'd_extra-i_favorite_band' in self.fields:
            self.fields['d_extra-i_favorite_band'] = forms.ChoiceField(
                required=False,
                choices=BLANK_CHOICE_DASH + i_choices(models.Song.BAND_CHOICES[:-1]),
                label=self.fields['d_extra-i_favorite_band'].label,
                initial=self.fields['d_extra-i_favorite_band'].initial,
            )
        self.reorder_fields([
            'm_description', 'location',
            'd_extra-i_favorite_band',
        ] + [
            'favorite_character{}'.format(nth)
            for nth in range(1, 4)
        ])

############################################################
# Accounts

class AccountForm(_AccountForm):
    level = forms.IntegerField(required=False, label=_('Level'), validators=[
        MinValueValidator(1),
        MaxValueValidator(300),
    ])
    start_date = forms.DateField(required=False, label=_('Start Date'), validators=[
        PastOnlyValidator,
        MinValueValidator(datetime.date(2017, 3, 16)),
    ])

    def __init__(self, *args, **kwargs):
        super(AccountForm, self).__init__(*args, **kwargs)
        if self.is_reported:
            for field in ['i_play_with', 'i_os']:
                if field in self.fields:
                    del(self.fields[field])
        if 'center' in self.fields:
            self.fields['center'].queryset = self.fields['center'].queryset.select_related('card').order_by('-card__release_date', '-card__id')
        if 'stargems_bought' in self.fields:
            self.fields['stargems_bought'].label = _('Total {item} bought').format(item=_('Star gems').lower())

    def save(self, commit=False):
        instance = super(AccountForm, self).save(commit=False)
        if instance.stargems_bought == 0:
            instance.stargems_bought = None
        if commit:
            instance.save()
        return instance

class AccountFilterForm(_AccountFilterForm):
    presets = OrderedDict([
        (_version, {
            'verbose_name': _version_details['translation'],
            'fields': {
                'i_version': models.Account.get_i('version', _version),
            },
            'image': u'language/{}.png'.format(_version_details['image']),
        }) for _version, _version_details in models.Account.VERSIONS.items()
    ])

    collected_card = forms.IntegerField(widget=forms.HiddenInput)
    collected_card_filter = MagiFilter(selector='cardscollectors__card_id')

############################################################
# Member

class MemberForm(AutoForm):
    def __init__(self, *args, **kwargs):
        super(MemberForm, self).__init__(*args, **kwargs)
        # Change labels for staff
        self.fields['square_image'].label = 'Small icon (for the map)'
        self.fields['square_image'].help_text = mark_safe('Example: <img src="https://i.bandori.party/u/i/m/1Toyama-Kasumi-D7Fpvu.png" height="40">')

    def save(self, commit=False):
        instance = super(MemberForm, self).save(commit=False)
        # Make sure all members use the same year as birthdate
        if instance.birthday:
            instance.birthday = instance.birthday.replace(year=2015)
        if instance.alt_name is not None and instance.japanese_alt_name is None:
            instance.japanese_alt_name = instance.alt_name
        # Invalidate cards cache
        if not self.is_creating:
            models.Card.objects.filter(member_id=instance.id).update(_cache_member_last_update=None)
        if commit:
            instance.save()
        return instance

    class Meta(AutoForm.Meta):
        model = models.Member
        fields = '__all__'

class MemberFilterForm(MagiFiltersForm):
    search_fields = ['name', 'japanese_name', 'school', 'CV', 'romaji_CV', 'classroom', 'food_like', 'food_dislike', 'instrument', 'hobbies', 'description']
    search_fields_labels = {
        'name': _('Name'),
        'CV': '',
    }

    ordering_fields = [
        ('id', _('Band')),
        ('_cache_total_fans', _('Most popular')),
        ('name', _('Name')),
        ('japanese_name', string_concat(_('Name'), ' (', t['Japanese'], ')')),
        ('birthday', _('Birthday')),
        ('height', _('Height')),
        ('color', _('Color')),
    ]

    school = forms.ChoiceField(label=_('School'), choices=BLANK_CHOICE_DASH + [(s, s) for s in getattr(django_settings, 'SCHOOLS', [])], initial=None)

    class Meta(MagiFiltersForm.Meta):
        model = models.Member
        fields = ('search', 'i_band', 'school', 'i_school_year', 'i_astrological_sign')

############################################################
# Card

class CardForm(AutoForm):
    def __init__(self, *args, **kwargs):
        super(CardForm, self).__init__(*args, **kwargs)
        self.previous_member_id = None if self.is_creating else self.instance.member_id

    def clean(self):
        cleaned_data = super(CardForm, self).clean()
        special = cleaned_data.get('i_skill_special')
        if special:
            skill_type = cleaned_data.get('i_skill_type')
            special_key = models.Card.SKILL_SPECIAL_CHOICES[special][0]
            if special_key not in models.Card.SKILL_TYPES[skill_type].get('special_templates', {}):
                raise forms.ValidationError('Skill special case is not valid for the card\'s skill type.')

        return cleaned_data

    def save(self, commit=False):
        instance = super(CardForm, self).save(commit=False)
        if self.previous_member_id != instance.member_id:
            instance.update_cache('member')
        instance.save()

        # members can't cameo in their own cards
        instance.cameo_members = filter(lambda x: x.id != instance.member_id, self.cleaned_data['cameo_members'])
        instance.update_cache('cameos')
        return instance

    class Meta(AutoForm.Meta):
        model = models.Card
        fields = '__all__'
        optional_fields = ('cameo_members',)

class CardFilterForm(MagiFiltersForm):
    search_fields = ['_cache_j_member', 'name', 'japanese_name', 'skill_name', 'japanese_skill_name']
    search_fields_labels = {
        '_cache_j_member': _('Member'),
    }
    ordering_fields = [
        ('release_date,id', _('Release date')),
        ('id', _('ID')),
        ('_cache_total_collectedcards', lambda: string_concat(_('Most popular'), ' (', _('Collected {things}').format(things=_('Cards').lower()), ')')),
        ('_cache_total_favorited', lambda: string_concat(_('Most popular'), ' (', _('Favorite {things}').format(things=_('Cards').lower()), ')')),
        ('member__name', string_concat(_('Member'), ' - ', _('Name'))),
        ('member__japanese_name', string_concat(_('Member'), ' - ', _('Name'), ' (', t['Japanese'], ')')),
        ('i_rarity', _('Rarity')),
        ('i_attribute', _('Attribute')),
        ('performance_max', _('Performance')),
        ('performance_trained_max', string_concat(_('Performance'), ' (', _('Trained'), ')')),
        ('technique_max', _('Technique')),
        ('technique_trained_max', string_concat(_('Technique'), ' (', _('Trained'), ')')),
        ('visual_max', _('Visual')),
        ('visual_trained_max', string_concat(_('Visual'), ' (', _('Trained'), ')')),
        ('_overall_max', _('Overall')),
        ('_overall_trained_max', string_concat(_('Overall'), ' (', _('Trained'), ')')),
    ]

    presets = OrderedDict([
        ('{}-stars'.format(_rarity), {
            'verbose_name': _verbose_name,
            'fields': {
                'i_rarity': _rarity,
            },
            'image': 'star_trained.png' if _rarity in models.Card.TRAINABLE_RARITIES else 'star_untrained.png',
        }) for _rarity, _verbose_name in dict(models.Card.RARITY_CHOICES).items()
    ] + [
        (_attribute['english'], {
            'verbose_name': _attribute['translation'],
            'fields': {
                'i_attribute': _i,
            },
            'image': u'i_attribute/{}.png'.format(_i),
        }) for _i, _attribute in models.Card.ATTRIBUTES.items()
    ] + [
        (_band_name, {
            'verbose_name': _band_name,
            'fields': {
                'member_band': u'band-{}'.format(_i_band),
            },
            'image': u'mini_band/{}.png'.format(_band_name),
        }) for _i_band, _band_name in i_choices(models.Member.BAND_CHOICES)
    ] + [
        (_name, {
            'verbose_name': _name,
            'fields': {
                'member_band': u'member-{}'.format(_id),
            },
            'image': _image,
        }) for (_id, _name, _image) in getattr(django_settings, 'FAVORITE_CHARACTERS', [])
    ])

    def __init__(self, *args, **kwargs):
        super(CardFilterForm, self).__init__(*args, **kwargs)
        if 'gacha_type' in self.fields:
            self.fields['gacha_type'].choices = [
                (k, models.DREAMFES_PER_LANGUAGE.get(get_language(), v) if k == 'dreamfes' else v)
                for k, v in self.fields['gacha_type'].choices
            ]

    # Skill filter

    def skill_filter_to_queryset(self, queryset, request, value):
        if not value: return queryset
        if value == '1': return queryset.filter(i_skill_type=value) # Score up
        return queryset.filter(Q(i_skill_type=value) | Q(i_side_skill_type=value))
    i_skill_type_filter = MagiFilter(to_queryset=skill_filter_to_queryset)

    # Member + band filter

    _member_band_to_queryset = member_band_to_queryset()
    def member_band_cameos_to_queryset(self, queryset, request, value):
        if self.data.get('member_includes_cameos'):
            value = value[7:]
            return queryset.filter(Q(member_id=value) | Q(cameo_members__id=value))
        return self._member_band_to_queryset(queryset, request, value)

    member_band = MEMBER_BAND_CHOICE_FIELD
    member_band_filter = MagiFilter(to_queryset=member_band_cameos_to_queryset)

    member_includes_cameos = forms.BooleanField(label=_('Include cameos'))
    member_includes_cameos_filter = MagiFilter(noop=True)

    # Origin filter

    def _origin_to_queryset(self, queryset, request, value):
        if value == 'is_original':
            return queryset.filter(is_original=True)
        elif value == 'is_promo':
            return queryset.filter(is_promo=True)
        elif value == 'is_gacha':
            return queryset.filter(_cache_j_gachas__isnull=False)
        elif value == 'is_event':
            return queryset.filter(_cache_j_events__isnull=False)
        return queryset

    origin = forms.ChoiceField(label=_(u'Origin'), choices=BLANK_CHOICE_DASH + [
        ('is_original', _(u'Original card')),
        ('is_event', _(u'Event')),
        ('is_gacha', _(u'Gacha')),
        ('is_promo', _(u'Promo')),
    ])
    origin_filter = MagiFilter(to_queryset=_origin_to_queryset)

    def _gacha_type_to_queryset(self, queryset, request, value):
        if value == 'permanent':
            return queryset.filter(gachas__limited=False, gachas__dreamfes=False)
        elif value == 'limited':
            return queryset.filter(gachas__limited=True)
        elif value == 'dreamfes':
            return queryset.filter(gachas__dreamfes=True)
        return queryset

    gacha_type = forms.ChoiceField(label=_(u'Gacha type'), choices=BLANK_CHOICE_DASH + models.Gacha.GACHA_TYPES)
    gacha_type_filter = MagiFilter(to_queryset=_gacha_type_to_queryset)

    # View filter

    def _view_to_queryset(self, queryset, request, value):
        if value == 'art':
            return queryset.filter(art__isnull=False)
        elif value == 'transparent':
            return queryset.filter(transparent__isnull=False)
        return queryset

    view_filter = MagiFilter(to_queryset=_view_to_queryset)

    # Version filter

    version = forms.ChoiceField(label=_(u'Server availability'), choices=BLANK_CHOICE_DASH + models.Account.VERSION_CHOICES)
    version_filter = MagiFilter(to_queryset=lambda form, queryset, request, value: queryset.filter(c_versions__contains=value))

    class Meta(MagiFiltersForm.Meta):
        model = models.Card
        fields = ('view', 'search', 'member_band', 'member_includes_cameos', 'origin', 'gacha_type', 'i_rarity', 'i_attribute', 'i_skill_type', 'version', 'ordering', 'reverse_order', 'member')
        hidden_foreign_keys = ('member',)

############################################################
# CollectibleCard

def to_CollectibleCardForm(cls):
    class _CollectibleCardForm(cls.form_class):
        def __init__(self, *args, **kwargs):
            super(_CollectibleCardForm, self).__init__(*args, **kwargs)
            if 'first_episode' in self.fields:
                self.fields['first_episode'].label = _('{nth} episode').format(nth=_('1st'))
            rarity = int(self.collectible_variables['i_rarity'])
            if rarity and rarity not in models.Card.TRAINABLE_RARITIES and 'trained' in self.fields:
                del(self.fields['trained'])
                if 'prefer_untrained' in self.fields:
                    del(self.fields['prefer_untrained'])

        def save(self, commit=True):
            instance = super(_CollectibleCardForm, self).save(commit=False)
            if instance.card.i_rarity not in models.Card.TRAINABLE_RARITIES:
                instance.trained = False
            if commit:
                instance.save()
            return instance
    return _CollectibleCardForm

def to_CollectibleCardFilterForm(cls):
    class _CollectibleCardFilterForm(cls.ListView.filter_form):
        ordering_fields = [('card__i_rarity,trained,card__release_date', _('Default'))] + cls.ListView.filter_form.ordering_fields

        def skill_filter_to_queryset(self, queryset, request, value):
            if not value: return queryset
            if value == '1': return queryset.filter(card__i_skill_type=value) # Score up
            return queryset.filter(Q(card__i_skill_type=value) | Q(card__i_side_skill_type=value))

        member_band = MEMBER_BAND_CHOICE_FIELD
        member_band_filter = MagiFilter(to_queryset=member_band_to_queryset(prefix='card__'))

        i_rarity = forms.ChoiceField(choices=BLANK_CHOICE_DASH + list(models.Card.RARITY_CHOICES), label=_('Rarity'))
        i_rarity_filter = MagiFilter(selector='card__i_rarity')

        i_attribute = forms.ChoiceField(choices=BLANK_CHOICE_DASH + list(models.Card.ATTRIBUTE_CHOICES), label=_('Attribute'))
        i_attribute_filter = MagiFilter(selector='card__i_attribute')

        i_skill_type = forms.ChoiceField(choices=BLANK_CHOICE_DASH
                                               + models.Card.SKILL_TYPE_CHOICES, label=_('Skill'))
        i_skill_type_filter = MagiFilter(to_queryset=skill_filter_to_queryset)
    return _CollectibleCardFilterForm

############################################################
# Event

class EventForm(AutoForm):
    start_date = forms.DateField(label=_('Beginning'))
    end_date = forms.DateField(label=_('End'))

    english_start_date = forms.DateField(label=string_concat(_('English version'), ' - ', _('Beginning')), required=False)
    english_end_date = forms.DateField(label=string_concat(_('English version'), ' - ', _('End')), required=False)

    taiwanese_start_date = forms.DateField(label=string_concat(_('Taiwanese version'), ' - ', _('Beginning')), required=False)
    taiwanese_end_date = forms.DateField(label=string_concat(_('Taiwanese version'), ' - ', _('End')), required=False)

    korean_start_date = forms.DateField(label=string_concat(_('Korean version'), ' - ', _('Beginning')), required=False)
    korean_end_date = forms.DateField(label=string_concat(_('Korean version'), ' - ', _('End')), required=False)

    def __init__(self, *args, **kwargs):
        super(EventForm, self).__init__(*args, **kwargs)
        if not self.is_creating:
            self.instance.previous_main_card_id = self.instance.main_card_id
            self.instance.previous_secondary_card_id = self.instance.secondary_card_id

        # Exclude invalid cards
        for prefix in ['main', 'secondary']:
            try:
                queryset = self.fields['{}_card'.format(prefix)].queryset.filter(
                    gachas__isnull=True,
                    is_promo=False,
                    is_original=False,
                )
            except KeyError:
                continue
            if not self.is_creating:
                queryset = queryset.filter(
                    Q(main_card_event__isnull=True, secondary_card_event__isnull=True)
                    | Q(**{ '{}_card_event__id'.format(prefix): self.instance.id }),
                )
            else:
                queryset = queryset.filter(main_card_event__isnull=True, secondary_card_event__isnull=True)
            self.fields['{}_card'.format(prefix)].queryset = queryset

        if 'c_versions' in self.fields:
            del(self.fields['c_versions'])

    def _clean_card_rarity(self, field_name, rarities):
        if field_name in self.cleaned_data and self.cleaned_data[field_name]:
            if self.cleaned_data[field_name].i_rarity not in rarities:
                raise forms.ValidationError(u'Rarity must be one of {}'.format(tuple(rarities)))
            return self.cleaned_data[field_name]
        return None

    def clean_main_card(self):
        return self._clean_card_rarity('main_card', models.Event.MAIN_CARD_ALLOWED_RARITIES)

    def clean_secondary_card(self):
        return self._clean_card_rarity('secondary_card', models.Event.SECONDARY_CARD_ALLOWED_RARITIES)

    def save(self, commit=False):
        instance = super(EventForm, self).save(commit=False)
        # None Event Stat Boost if not a Song Ranking Type
        if instance.type not in models.Event.SONG_RANKING_TYPES:
            instance.i_boost_stat = None
        # Set the right time for each version
        for version, times in instance.TIMES_PER_VERSIONS.items():
            version_details = instance.VERSIONS[version]
            for field_name, time in zip(('start_date', 'end_date'), times):
                field_name = u'{prefix}{field_name}'.format(
                    prefix=version_details['prefix'],
                    field_name=field_name,
                )
                value = getattr(instance, field_name)
                if value:
                    setattr(instance, field_name, value.replace(hour=time[0], minute=time[1]))
        # Toggle versions based on start date field
        instance.save_c('versions', [
            value for prefix, value in (
                ('', 'JP'),
                ('english_', 'EN'),
                ('taiwanese_', 'TW'),
                ('korean_', 'KR'),
            ) if getattr(instance, u'{}start_date'.format(prefix))])
        if commit:
            instance.save()
        return instance

    class Meta(AutoForm.Meta):
        model = models.Event
        fields = '__all__'
        optional_fields = ('boost_members',)

class EventFilterForm(MagiFiltersForm):
    search_fields = ['name', 'japanese_name']
    ordering_fields = [
        ('start_date', string_concat(_('Date'), ' (', _('Japanese version'), ')')),
        ('english_start_date', string_concat(_('Date'), ' (', _('English version'), ')')),
        ('taiwanese_start_date', string_concat(_('Date'), ' (', _('Taiwanese version'), ')')),
        ('korean_start_date', string_concat(_('Date'), ' (', _('Korean version'), ')')),
        ('_cache_total_participations', string_concat(_('Most popular'), ' (', _('Participated events'), ')')),
        ('name', _('Title')),
        ('japanese_name', string_concat(_('Title'), ' (', t['Japanese'], ')')),
    ]

    boost_members = forms.ChoiceField(choices=BLANK_CHOICE_DASH + [(id, full_name) for (id, full_name, image) in getattr(django_settings, 'FAVORITE_CHARACTERS', [])], initial=None, label=_('Boost members'))

    version = forms.ChoiceField(label=_(u'Server availability'), choices=BLANK_CHOICE_DASH + models.Account.VERSION_CHOICES)
    version_filter = MagiFilter(to_queryset=lambda form, queryset, request, value: queryset.filter(c_versions__contains=value))

    def _status_to_queryset(self, queryset, request, value):
        prefix = ''
        if self.data.get('version'):
            prefix = models.Event.VERSIONS[self.data.get('version')]['prefix']
        return filterEventsByStatus(queryset, value, prefix=prefix)

    status = forms.ChoiceField(label=_('Status'), choices=BLANK_CHOICE_DASH + [
        ('ended', _('Past')),
        ('current', _('Current')),
        ('future', _('Future')),
    ])
    status_filter = MagiFilter(to_queryset=_status_to_queryset)

    class Meta(MagiFiltersForm.Meta):
        model = models.Event
        fields = ('view', 'search', 'i_type', 'boost_members', 'i_boost_stat', 'i_boost_attribute', 'version', 'status', 'ordering', 'reverse_order')

############################################################
# Event participations form

def to_EventParticipationForm(cls):
    class _EventParticipationForm(cls.form_class):
        def __init__(self, *args, **kwargs):
            super(_EventParticipationForm, self).__init__(*args, **kwargs)
            i_type = int(self.collectible_variables['i_type'])
            if models.Event.get_reverse_i('type', i_type) not in models.Event.SONG_RANKING_TYPES:
                for field in ['song_score', 'song_ranking']:
                    if field in self.fields:
                        del(self.fields[field])
            if models.Event.get_reverse_i('type', i_type) not in models.Event.GOAL_MASTER_TYPES:
                for field in ['is_goal_master', 'is_ex_goal_master']:
                    if field in self.fields:
                        del(self.fields[field])

        def clean(self):
            cleaned_data = super(_EventParticipationForm, self).clean()

            # Variables to simplify conditionals
            version = getattr(cleaned_data.get('account', None), 'version', 'EN')
            screenshot = cleaned_data.get('screenshot', None)
            is_playground = getattr(cleaned_data.get('account', None), 'is_playground', False)

            # If Rank is under X, Require Screenshot
            if is_playground == False and screenshot == None and cleaned_data.get('ranking') != None:
                if cleaned_data.get('ranking') <= models.Event.MAX_RANK_WITHOUT_SS[version]:
                    raise forms.ValidationError(
                        message=_('Please provide a screenshot to prove your ranking.'),
                        code='ranking_proof_screenshot',
                    )
            return cleaned_data

        #Note: Check if ranking exists first and skips if playground to avoid unncessary checks

        class Meta(cls.form_class.Meta):
            optional_fields = ('score', 'ranking', 'song_score', 'song_ranking')

    return _EventParticipationForm

def to_EventParticipationFilterForm(cls):
    class _EventParticipationFilterForm(cls.ListView.filter_form):
        ordering_fields = [
            ('id', _('Creation')),
            ('ranking', _('Ranking')),
            ('score', _('Score')),
            ('song_score', _('Song score')),
            ('song_ranking', _('Song ranking')),
        ] + [(u'event__{}'.format(_o), _t) for _o, _t in EventFilterForm.ordering_fields]

        i_version = forms.ChoiceField(label=_('Version'), choices=BLANK_CHOICE_DASH + i_choices(models.Account.VERSION_CHOICES))
        i_version_filter = MagiFilter(selector='account__i_version')

        # TODO: event type, boost members, boost attribute

        def __init__(self, *args, **kwargs):
            super(_EventParticipationFilterForm, self).__init__(*args, **kwargs)
            if 'view' in self.fields and self.request.GET.get('view', None) != 'leaderboard':
                del(self.fields['view'])

        class Meta(cls.ListView.filter_form.Meta):
            fields = ('view', 'search', 'i_version', 'ordering', 'reverse_order')

    return _EventParticipationFilterForm

############################################################
# Gacha

class GachaForm(AutoForm):
    start_date = forms.DateField(label=_('Beginning'))
    end_date = forms.DateField(label=_('End'))

    english_start_date = forms.DateField(label=string_concat(_('English version'), ' - ', _('Beginning')), required=False)
    english_end_date = forms.DateField(label=string_concat(_('English version'), ' - ', _('End')), required=False)

    taiwanese_start_date = forms.DateField(label=string_concat(_('Taiwanese version'), ' - ', _('Beginning')), required=False)
    taiwanese_end_date = forms.DateField(label=string_concat(_('Taiwanese version'), ' - ', _('End')), required=False)

    korean_start_date = forms.DateField(label=string_concat(_('Korean version'), ' - ', _('Beginning')), required=False)
    korean_end_date = forms.DateField(label=string_concat(_('Korean version'), ' - ', _('End')), required=False)

    def __init__(self, *args, **kwargs):
        super(GachaForm, self).__init__(*args, **kwargs)

        # Exclude invalid cards
        if 'cards' in self.fields:
            queryset = self.fields['cards'].queryset.filter(
                main_card_event__isnull=True,
                secondary_card_event__isnull=True,
                is_promo=False,
                is_original=False,
            )
            if self.is_creating:
                queryset = queryset.filter(gachas__isnull=True)
            elif not self.instance.dreamfes:
                queryset = queryset.filter(Q(gachas__isnull=True) | Q(gachas__id=self.instance.id))
            self.fields['cards'].queryset = queryset

        if 'c_versions' in self.fields:
            del(self.fields['c_versions'])

    def clean_japanese_name(self):
        _name = self.cleaned_data.get('japanese_name')
        return _name[:-3] if _name.endswith(u'ガチャ') else _name

    def save(self, commit=False):
        instance = super(GachaForm, self).save(commit=False)
        # Set the right time for each version
        for version, times in instance.TIMES_PER_VERSIONS.items():
            version_details = instance.VERSIONS[version]
            for field_name, time in zip(('start_date', 'end_date'), times):
                field_name = u'{prefix}{field_name}'.format(
                    prefix=version_details['prefix'],
                    field_name=field_name,
                )
                value = getattr(instance, field_name)
                if value:
                    setattr(instance, field_name, value.replace(hour=time[0], minute=time[1]))
        # Toggle versions based on start date field
        instance.save_c('versions', [
            value for prefix, value in (
                ('', 'JP'),
                ('english_', 'EN'),
                ('taiwanese_', 'TW'),
                ('korean_', 'KR'),
            ) if getattr(instance, u'{}start_date'.format(prefix))])
        if commit:
            instance.save()
        return instance

    class Meta(AutoForm.Meta):
        model = models.Gacha
        fields = '__all__'
        optional_fields = ('cards',)

class GachaFilterForm(MagiFiltersForm):
    search_fields = ['name', 'japanese_name']
    ordering_fields = [
        ('start_date', string_concat(_('Date'), ' (', _('Japanese version'), ')')),
        ('english_start_date', string_concat(_('Date'), ' (', _('English version'), ')')),
        ('taiwanese_start_date', string_concat(_('Date'), ' (', _('Taiwanese version'), ')')),
        ('korean_start_date', string_concat(_('Date'), ' (', _('Korean version'), ')')),
        ('name', _('Title')),
        ('japanese_name', string_concat(_('Title'), ' (', t['Japanese'], ')')),
    ]

    def _gacha_type_to_queryset(self, queryset, request, value):
        if value == 'permanent':
            return queryset.filter(limited=False, dreamfes=False)
        elif value == 'limited':
            return queryset.filter(limited=True)
        elif value == 'dreamfes':
            return queryset.filter(dreamfes=True)
        return queryset

    gacha_type = forms.ChoiceField(label=_(u'Gacha type'), choices=BLANK_CHOICE_DASH + models.Gacha.GACHA_TYPES)
    gacha_type_filter = MagiFilter(to_queryset=_gacha_type_to_queryset)

    featured_member = forms.ChoiceField(choices=BLANK_CHOICE_DASH + [(id, full_name) for (id, full_name, image) in getattr(django_settings, 'FAVORITE_CHARACTERS', [])], initial=None, label=_('Member'))
    featured_member_filter = MagiFilter(selector='cards__member_id')

    version = forms.ChoiceField(label=_(u'Server availability'), choices=BLANK_CHOICE_DASH + models.Account.VERSION_CHOICES)
    version_filter = MagiFilter(to_queryset=lambda form, queryset, request, value: queryset.filter(c_versions__contains=value))

    def _status_to_queryset(self, queryset, request, value):
        prefix = ''
        if self.data.get('version'):
            prefix = models.Gacha.VERSIONS[self.data.get('version')]['prefix']
        return filterEventsByStatus(queryset, value, prefix=prefix)

    status = forms.ChoiceField(label=_('Status'), choices=BLANK_CHOICE_DASH + [
        ('ended', _('Past')),
        ('current', _('Current')),
        ('future', _('Future')),
    ])
    status_filter = MagiFilter(to_queryset=_status_to_queryset)

    def __init__(self, *args, **kwargs):
        super(GachaFilterForm, self).__init__(*args, **kwargs)
        if 'gacha_type' in self.fields:
            self.fields['gacha_type'].choices = [
                (k, models.DREAMFES_PER_LANGUAGE.get(get_language(), v) if k == 'dreamfes' else v)
                for k, v in self.fields['gacha_type'].choices
            ]

    class Meta(MagiFiltersForm.Meta):
        model = models.Gacha
        fields = ('search', 'gacha_type', 'featured_member', 'i_attribute', 'version', 'status', 'ordering', 'reverse_order')

############################################################
# Rerun gacha event

class RerunForm(AutoForm):
    start_date = forms.DateField(label=_('Beginning'))
    end_date = forms.DateField(label=_('End'))

    def __init__(self, *args, **kwargs):
        super(RerunForm, self).__init__(*args, **kwargs)
        # When editing
        if not self.is_creating:
            # Don't allow to edit item
            for item in models.Rerun.ITEMS:
                if item in self.fields:
                    del(self.fields[item])
            # Don't allow to edit version
            del(self.fields['i_version'])
        else:
            # When adding
            # When version specified in GET
            i_version = None
            if 'i_version' in self.request.GET:
                i_version = int(self.request.GET['i_version'])
                self.fields['i_version'].widget = forms.HiddenInput()
                self.fields['i_version'].initial = i_version
            item_id = None
            for item in models.Rerun.ITEMS:
                if i_version is not None:
                    self.fields[item].queryset = self.fields[item].queryset.filter(c_versions__contains=u'"{}"'.format(models.Rerun.get_reverse_i('version', i_version)))
                # When item specified in GET
                if u'{}_id'.format(item) in self.request.GET:
                    item_id = self.request.GET[u'{}_id'.format(item)]
                    if not item_id:
                        continue
                    # Hide all other fields
                    for other_item in models.Rerun.ITEMS:
                        if other_item != item and other_item in self.fields:
                            del(self.fields[other_item])
                    # Set item field as hidden
                    self.fields[item] = HiddenModelChoiceField(
                        queryset=self.fields[item].queryset,
                        initial=item_id,
                    )
                    break
            if item_id or i_version is not None:
                self.beforefields = mark_safe(u'<div class="col-sm-offset-4">{item}{version}</div><br>'.format(
                    item=u'<p>Adding to <a href="/{item}/{id}/">{item} #{id}</a></p>'.format(
                        item=item, id=item_id,
                    ) if item_id else '',
                    version=u'<p><img src="{image}" alt="{version}" height="30" /> {version}</p>'.format(
                        version=models.Rerun.get_verbose_i('version', i_version),
                        image=staticImageURL(
                            models.Account.VERSIONS[models.Rerun.get_reverse_i('version', i_version)]['image'],
                            folder='language', extension='png',
                        ),
                    ) if i_version is not None else '',
                ))


    def clean(self):
        cleaned_data = super(RerunForm, self).clean()
        if self.is_creating:
            # Check that there's one and only one item
            selected_item = None
            for item in models.Rerun.ITEMS:
                if cleaned_data.get(item, None):
                    selected_item = cleaned_data.get(item, None)
                    for other_item in models.Rerun.ITEMS:
                        if item != other_item and cleaned_data.get(other_item, None):
                            raise forms.ValidationError(u'You can\'t have {} + {}, select only one.'.format(item, other_item))
                    break
            if not selected_item:
                raise forms.ValidationError(u'You need at least one {}.'.format(' or '.join(models.Rerun.ITEMS)))
            # Check that item already ran before for that version
            i_version = self.cleaned_data.get('i_version', None)
            if i_version is not None:
                if models.Rerun.get_reverse_i('version', i_version) not in selected_item.versions:
                    raise forms.ValidationError(u'The {item} "{item_name}" is not available in {version}'.format(
                        item=item, item_name=unicode(selected_item), version=models.Rerun.get_verbose_i('version', i_version),
                    ))
            return cleaned_data

    def save(self, commit=False):
        instance = super(RerunForm, self).save(commit=False)
        # Set the right time based on version
        version_details = instance.VERSIONS[instance.version]
        times = next(model for item, model in models.Rerun.ITEMS_MODELS.items()
                    if getattr(instance, item, None)).TIMES_PER_VERSIONS[instance.version]
        instance.start_date = instance.start_date.replace(hour=times[0][0], minute=times[0][1])
        instance.end_date = instance.end_date.replace(hour=times[1][0], minute=times[1][1])
        if commit:
            instance.save()
        return instance

    class Meta(AutoForm.Meta):
        model = models.Rerun
        fields = '__all__'

############################################################
# Played song

def to_PlayedSongForm(cls):
    class _PlayedSongForm(cls.form_class):
        class Meta(cls.form_class.Meta):
            optional_fields = ('score', 'screenshot')
    return _PlayedSongForm

def to_PlayedSongFilterForm(cls):
    class _PlayedSongFilterForm(cls.ListView.filter_form):
        ordering_fields = [
            ('id', _('Creation')),
            ('score', _('Score')),
        ] + cls.ListView.filter_form.ordering_fields

        i_version = forms.ChoiceField(label=_('Version'), choices=BLANK_CHOICE_DASH + i_choices(models.Account.VERSION_CHOICES))
        i_version_filter = MagiFilter(selector='account__i_version')

        screenshot = forms.NullBooleanField(label=_('Screenshot'))
        screenshot_filter = MagiFilter(selector='screenshot__isnull')

        # TODO: band, unlock, cover

        def __init__(self, *args, **kwargs):
            super(_PlayedSongFilterForm, self).__init__(*args, **kwargs)
            if 'view' in self.fields and self.request.GET.get('view', None) != 'leaderboard':
                self.fields['view'].choices = [(k, v) for k, v in self.fields['view'].choices if k != 'leaderboard']

        class Meta(cls.ListView.filter_form.Meta):
            fields = ('view', 'search', 'i_version', 'i_difficulty', 'full_combo', 'all_perfect', 'screenshot', 'ordering', 'reverse_order')

    return _PlayedSongFilterForm

############################################################
# Song

class _SongForm(AutoForm):

    def __init__(self, *args, **kwargs):
        super(_SongForm, self).__init__(*args, **kwargs)
        if 'i_unlock' in self.fields:
            del(self.fields['i_unlock'])
        if 'c_unlock_variables' in self.fields:
            del(self.fields['c_unlock_variables'])
        if 'length' in self.fields:
            self.fields['length'].help_text = 'in seconds'

    class Meta(AutoForm.Meta):
        model = models.Song
        fields = '__all__'

def unlock_to_form(unlock):
    class _UnlockSongForm(_SongForm):
        def __init__(self, *args, **kwargs):
            super(_UnlockSongForm, self).__init__(*args, **kwargs)
            help_text = mark_safe(u'Will be displayed as <code>{}</code>'.format(
                unicode(models.Song.UNLOCK[unlock]['template']).format(**{
                    variable: 'xxx'
                    for variable in models.Song.UNLOCK[unlock]['variables']
                }),
            )) if unlock != 'other' else None
            for i, variable in enumerate(models.Song.UNLOCK[unlock]['variables']):
                self.fields[variable] = forms.CharField(
                    help_text=help_text,
                    initial=None if self.is_creating else self.instance.unlock_variables[i],
                )
            if unlock != 'event' and 'event' in self.fields:
                del(self.fields['event'])
            if 'band' in self.fields:
                self.fields['band'] = forms.ChoiceField(
                    choices=BLANK_CHOICE_DASH + i_choices(models.Member.BAND_CHOICES),
                    help_text=self.fields['band'].help_text,
                    initial=self.fields['band'].initial,
                )

        def save(self, commit=False):
            instance = super(_UnlockSongForm, self).save(commit=False)
            instance.i_unlock = models.Song.get_i('unlock', unlock)
            instance.c_unlock_variables = join_data(*[
                self.cleaned_data[variable]
                for variable in models.Song.UNLOCK[unlock]['variables']
            ])
            if commit:
                instance.save()
            return instance

    return _UnlockSongForm

def to_translate_song_form_class(cls):
    class _TranslateSongForm(cls):
        class Meta(cls.Meta):
            fields = ['romaji_name'] + cls.Meta.fields
    return _TranslateSongForm

class SongFilterForm(MagiFiltersForm):
    search_fields = ['japanese_name', 'romaji_name', 'name', 'special_band', 'composer', 'lyricist', 'arranger']
    search_fields_labels = {
        'romaji_name': _('Title'),
        'name': '', 'special_band': '',
    }
    ordering_fields = [
        ('release_date', _('Release date')),
        ('japanese_name', _('Title')),
        ('_cache_total_played', string_concat(_('Most popular'), ' (', _('Played songs'), ')')),
        ('romaji_name', string_concat(_('Title'), ' (', _('Romaji'), ')')),
        ('length', _('Length')),
        ('bpm', _('BPM')),
        ('hard_notes', string_concat(_('Hard'), ' - ', _('Notes'))),
        ('hard_difficulty', string_concat(_('Hard'), ' - ', _('Difficulty'))),
        ('expert_notes', string_concat(_('Expert'), ' - ', _('Notes'))),
        ('expert_difficulty', string_concat(_('Expert'), ' - ', _('Difficulty'))),
        ('special_notes', string_concat(_('Special'), ' - ', _('Notes'))),
        ('special_difficulty', string_concat(_('Special'), ' - ', _('Difficulty'))),
    ]

    presets = OrderedDict([
        (_band_name, {
            'verbose_name': _band_name,
            'fields': {
                'i_band': _i_band,
            },
            'image': u'mini_band/{}.png'.format(_band_name),
        }) for _i_band, _band_name in i_choices(models.Song.BAND_CHOICES)
        if _band_name != 'Special Band'
    ])

    is_cover = forms.NullBooleanField(initial=None, required=False, label=_('Cover song'))
    is_cover_filter = MagiFilter(selector='is_cover')

    is_full = forms.NullBooleanField(initial=None, required=False, label=_('FULL version'))
    is_full_filter = MagiFilter(selector='is_full')

    sp_notes = forms.NullBooleanField(initial=None, required=False, label=_('{} notes').format('SP'))
    sp_notes_filter = MagiFilter(selector='sp_notes')

    version = forms.ChoiceField(label=_(u'Server availability'), choices=BLANK_CHOICE_DASH + models.Account.VERSION_CHOICES)
    version_filter = MagiFilter(to_queryset=lambda form, queryset, request, value: queryset.filter(c_versions__contains=value))

    class Meta(MagiFiltersForm.Meta):
        model = models.Song
        fields = ('search', 'i_band', 'i_unlock', 'is_cover', 'is_full', 'sp_notes', 'version', 'ordering', 'reverse_order')

############################################################
# AreaItem form

class AreaItemFilterForm(MagiFiltersForm):
    search_fields = ['name', 'd_names', 'about', 'd_abouts']

    def __init__(self, *args, **kwargs):
        super(AreaItemFilterForm, self).__init__(*args, **kwargs)
        if 'area' in self.fields:
            self.fields['area'].choices = BLANK_CHOICE_DASH + [
                (area['id'], area['d_names'].get(self.request.LANGUAGE_CODE, area['name']))
                for area in django_settings.AREAS
            ]

    area = forms.ChoiceField(label=_('Location'))

    band = forms.ChoiceField(label=_('Band'), choices=BLANK_CHOICE_DASH + [(i, band)
        for i, band in i_choices(models.Member.BAND_CHOICES)], initial=None)
    band_filter = MagiFilter(to_queryset=lambda form, queryset, request, value: queryset.filter(member__i_band=value))

    class Meta(MagiFiltersForm.Meta):
        model = models.AreaItem
        fields = ('search', 'area', 'i_type', 'i_instrument', 'band', 'i_attribute', 'i_boost_stat')

############################################################
# Item form

class ItemFilterForm(MagiFiltersForm):
    search_fields = ['name', 'm_description', 'd_names', 'd_m_descriptions']

    class Meta(MagiFiltersForm.Meta):
        model = models.Item
        fields = ('search', 'i_type')

############################################################
#CollectibleAreaItem form

def to_CollectibleAreaItemForm(cls):
    class _CollectibleAreaItemForm(cls.form_class):
        level = forms.IntegerField(required=True, label=_('Level'), validators=[
            MinValueValidator(1),
            MaxValueValidator(5),
        ], initial=1)

        def __init__(self, *args, **kwargs):
            super(_CollectibleAreaItemForm, self).__init__(*args, **kwargs)
            _max_level = int(self.collectible_variables.get('max_level'))
            if 'level' in self.fields:
                self.fields['level'].validators = [
                    MinValueValidator(1),
                    MaxValueValidator(_max_level),
                ]

    return _CollectibleAreaItemForm

def to_CollectibleAreaItemFilterForm(cls):
    class _CollectibleAreaItemFilterForm(cls.ListView.filter_form):
        area = forms.ChoiceField(label=_('Location'))
        area_filter = MagiFilter(selector='areaitem__area')

        i_type = forms.ChoiceField(label=_('Area'), choices=BLANK_CHOICE_DASH + i_choices(models.AreaItem.TYPE_CHOICES))
        i_type_filter = MagiFilter(selector='areaitem__i_type')

        i_instrument = forms.ChoiceField(label=_('Instrument'), choices=BLANK_CHOICE_DASH + i_choices(models.AreaItem.INSTRUMENT_CHOICES))
        i_instrument_filter = MagiFilter(selector='areaitem__i_instrument')

        i_attribute = forms.ChoiceField(label=_('Attribute'), choices=BLANK_CHOICE_DASH + models.AreaItem.ATTRIBUTE_CHOICES)
        i_attribute_filter = MagiFilter(selector='areaitem__i_attribute')

        i_boost_stat = forms.ChoiceField(label=_('Statistic'), choices=BLANK_CHOICE_DASH + i_choices(models.AreaItem.STAT_CHOICES))
        i_boost_stat_filter = MagiFilter(selector='areaitem__i_boost_stat')

        def __init__(self, *args, **kwargs):
            super(_CollectibleAreaItemFilterForm, self).__init__(*args, **kwargs)
            if 'area' in self.fields:
                self.fields['area'].choices = BLANK_CHOICE_DASH + [
                    (area['id'], area['d_names'].get(self.request.LANGUAGE_CODE, area['name']))
                     for area in django_settings.AREAS
                ]

        class Meta(cls.ListView.filter_form.Meta):
            fields = ('search', 'area', 'i_type', 'i_instrument', 'i_attribute', 'i_boost_stat')

    return _CollectibleAreaItemFilterForm

############################################################
# Asset form

def asset_type_to_form(_type):
    class _AssetForm(AutoForm):
        def __init__(self, *args, **kwargs):
            super(_AssetForm, self).__init__(*args, **kwargs)
            for variable in models.Asset.VARIABLES:
                if variable in self.fields and variable not in models.Asset.TYPES[_type]['variables']:
                    del(self.fields[variable])
            if 'i_type' in self.fields:
                del(self.fields['i_type'])
            if 'value' in self.fields:
                if _type == 'comic':
                    self.fields['value'] = forms.ChoiceField(label=_('Comics'), choices=(
                        BLANK_CHOICE_DASH + ASSET_COMICS_VALUE_PER_LANGUAGE['en']))
                # For CN art, remove incorrect version styling next to images
                elif _type == 'officialart':
                    self.fields['value'] = forms.ChoiceField(label='Add Version to Images', 
                        choices=([('1', 'Yes'), ('0', 'No')]),
                        help_text="If the art doesn't belong to a server we track, select No.",
                        initial='1'
                    )
            # Limit tags per type
            if 'c_tags' in self.fields:
                if _type == 'background':
                    self.fields['c_tags'].choices = models.Asset.BACKGROUND_TAGS
                elif _type == 'officialart':
                    self.fields['c_tags'].choices = models.Asset.OFFICIAL_TAGS

        def clean(self):
            cleaned_data = super(_AssetForm, self).clean()

            # Check that there is at least one image uploaded or already present
            for version in models.Account.VERSIONS.values():
                if (cleaned_data.get(u'{prefix}image'.format(prefix=version['prefix']), None)
                    or (not self.is_creating
                        and getattr(self.instance, u'{prefix}image'.format(prefix=version['prefix']), None))):
                    return cleaned_data
            raise forms.ValidationError('At least one image is required.')

        def save(self, commit=False):
            instance = super(_AssetForm, self).save(commit=False)
            instance.i_type = models.Asset.get_i('type', _type)
            if not instance.c_tags:
                instance.c_tags = None
            if commit:
                instance.save()
            return instance

        class Meta(AutoForm.Meta):
            model = models.Asset
            fields = '__all__'
    return _AssetForm

ASSET_COMICS_VALUE_PER_LANGUAGE = {
    'en': [('1', u'1-koma'), ('4', u'4-koma')],
    'ja': [('1', u'一コマ'), ('4', u'4コマ')],
    'kr': [('1', u'한 컷'), ('4', u'네 컷')],
    'zh-hans': [('1', u'单格'), ('4', u'四格')],
    'zh-hant': [('1', u'單格'), ('4', u'四格')],
}

def _get_asset_preset_label(type, things):
    return lambda: _('All {type} {things}').format(
        type=type, things=things.lower(),
    )
class AssetFilterForm(MagiFiltersForm):
    search_fields = ['name', 'd_names', 'c_tags', 'source', 'source_link']
    search_fields_labels = {'source_link': ''}

    presets = OrderedDict([
        (u'{}-{}'.format(_type, _band_name), {
            'verbose_name': _band_name,
            'label': _get_asset_preset_label(_band_name, _type_details['translation']),
            'fields': {
                'i_type': models.Asset.get_i('type', _type),
                'member_band': u'band-{}'.format(_i_band),
            },
            'image': u'mini_band/{}.png'.format(_band_name),
        }) for _i_band, _band_name in i_choices(models.Asset.BAND_CHOICES)
        for _type, _type_details in models.Asset.TYPES.items()
        if 'i_band' in _type_details['variables']
    ] + [
        (u'{}-{}'.format(_type, _name), {
            'verbose_name': _name,
            'label': _get_asset_preset_label(_name, _type_details['translation']),
            'fields': {
                'i_type': models.Asset.get_i('type', _type),
                'member_band': u'member-{}'.format(_id),
            },
            'image': _image,
        }) for (_id, _name, _image) in getattr(django_settings, 'FAVORITE_CHARACTERS', [])
        for _type, _type_details in models.Asset.TYPES.items()
        if 'members' in _type_details['variables']
    ] + [
        (_type, {
            'label': _type_details['translation'],
            'fields': {
                'i_type': models.Asset.get_i('type', _type),
            },
            'image': _type_details.get('image', None),
            'icon': _type_details.get('icon', None),
        }) for _type, _type_details in models.Asset.TYPES.items()
    ])

    is_event = forms.NullBooleanField(label=_('Event'))
    is_event_filter = MagiFilter(selector='event__isnull')

    is_song = forms.NullBooleanField(label=_('Song'))
    is_song_filter = MagiFilter(selector='song__isnull')

    def members_to_queryset(self, queryset, request, value):
        member = models.Member.objects.get(id=value)
        return queryset.filter(Q(members=member) | Q(i_band=member.i_band)).distinct()

    members = forms.ChoiceField(choices=BLANK_CHOICE_DASH + [
        (id, full_name) for (id, full_name, image) in getattr(django_settings, 'FAVORITE_CHARACTERS', [])
    ], initial=None, label=_('Member'))
    members_filter = MagiFilter(to_queryset=members_to_queryset)

    def members_band_to_queryset(self, queryset, request, value):
        if value.startswith('member-'):
            return self.members_to_queryset(queryset, request, value[7:])
        elif value.startswith('band-'):
            return queryset.filter(Q(i_band=value[5:]) | Q(members__i_band=value[5:])).distinct()
        return queryset

    member_band = MEMBER_BAND_CHOICE_FIELD
    member_band_filter = MagiFilter(to_queryset=members_band_to_queryset)

    def _i_version_to_queryset(self, queryset, request, value):
        prefix = models.Account.VERSIONS_PREFIXES.get(models.Account.get_reverse_i('version', int(value)))
        return queryset.filter(**{u'{}image__isnull'.format(prefix): False}).exclude(**{u'{}image'.format(prefix): ''}).exclude(**{u'value': '0'})

    i_version = forms.ChoiceField(label=_('Version'), choices=BLANK_CHOICE_DASH + i_choices(models.Account.VERSION_CHOICES))
    i_version_filter = MagiFilter(to_queryset=_i_version_to_queryset)

    i_band_filter = MagiFilter(selectors=['i_band', 'members__i_band'], distinct=True)

    value = forms.ChoiceField(label=_('Comics'), choices=BLANK_CHOICE_DASH + ASSET_COMICS_VALUE_PER_LANGUAGE['en'])

    event = forms.IntegerField(widget=forms.HiddenInput)
    song = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super(AssetFilterForm, self).__init__(*args, **kwargs)
        # Get type from request or preset
        try:
            self.selected_type = models.Asset.get_reverse_i('type', int(self.request.GET.get('i_type', None)))
        except (KeyError, ValueError, TypeError):
            self.selected_type = self.preset.split('-')[0] if self.preset else None
        # Make sure the form always uses presets URLs
        if self.selected_type:
            self.action_url = self.collection.get_list_url(preset=self.selected_type)
        # Show only variables that match type
        if self.selected_type in models.Asset.TYPES:
            for variable in models.Asset.VARIABLES:
                if (variable in self.fields
                    and variable not in (
                        models.Asset.TYPES[self.selected_type]['variables']
                        + (['i_band'] if 'members' in models.Asset.TYPES[self.selected_type]['variables'] else [])
                    )):
                    del(self.fields[variable])
            if 'i_type' in self.fields:
                self.fields['i_type'].widget = forms.HiddenInput()
        # Initial version for comics based on user language
        if 'i_version' in self.fields and self.selected_type == 'comic':
            version = models.LANGUAGES_TO_VERSIONS.get(self.request.LANGUAGE_CODE, None)
            if version:
                self.fields['i_version'].initial = models.Account.get_i('version', version)
        # Remove value filter except for comic
        if 'value' in self.fields:
            if self.selected_type == 'comic':
                self.fields['value'].choices = BLANK_CHOICE_DASH + ASSET_COMICS_VALUE_PER_LANGUAGE.get(
                    self.request.LANGUAGE_CODE,
                    ASSET_COMICS_VALUE_PER_LANGUAGE['en'],
                )
            else:
                del(self.fields['value'])
        # Remove is event from fields if type can't be linked with events
        if 'event' not in self.fields and 'is_event' in self.fields:
            del(self.fields['is_event'])
        # Only show is song filter for titles+official art
        if self.selected_type and self.selected_type not in ['title', 'officialart'] and 'is_song' in self.fields:
            del(self.fields['is_song'])
        # Replace band + member with member_band filter
        if 'i_band' in self.fields and 'members' in self.fields:
            self.fields['i_band'].widget = self.fields['i_band'].hidden_widget()
            self.fields['members'].widget = self.fields['members'].hidden_widget()
        else:
            del(self.fields['member_band'])
        # Remove help text of band
        if 'i_band' in self.fields:
            self.fields['i_band'].help_text = None
        # Limit tags per type
        if 'c_tags' in self.fields:
            if self.selected_type == 'background':
                self.fields['c_tags'].choices = models.Asset.BACKGROUND_TAGS
            elif self.selected_type == 'officialart':
                self.fields['c_tags'].choices = models.Asset.OFFICIAL_TAGS

    @property
    def extra_buttons(self):
        buttons = MagiFiltersForm.extra_buttons.fget(self)
        if 'clear' in buttons and self.selected_type:
            buttons['clear']['url'] = self.collection.get_list_url(preset=self.selected_type)
        return buttons

    class Meta(MagiFiltersForm.Meta):
        model = models.Asset
        fields = ['search', 'i_type', 'member_band', 'is_event', 'is_song'] + [
            v for v in models.Asset.VARIABLES if v not in ['name', 'source', 'source_link']
        ] + ['i_version']

############################################################
# Costume form

class CostumeForm(AutoForm):
    chibis = MultiImageField(min_num=0, max_num=10, required=False, label='Add chibi images')

    def __init__(self, *args, **kwargs):
        super(CostumeForm, self).__init__(*args, **kwargs)

        if not self.is_creating:
            # chibi delete fields
            self.all_chibis = self.instance.owned_chibis.all()
            for imageObject in self.all_chibis:
                self.fields[u'delete_chibi_{}'.format(imageObject.id)] = forms.BooleanField(
                    label=mark_safe(u'Delete chibi <img src="{}" height="100" />'.format(imageObject.image_url)),
                    initial=False, required=False,
                )

        q = Q(associated_costume__isnull=True)
        if self.instance.card:
            q |= Q(associated_costume=self.instance)
        self.fields['card'].queryset = self.fields['card'].queryset.filter(q)

        self.fields['member'].help_text = 'If associating this costume with a card, you can leave this blank. I\'ll take the member from the card.'

    def has_at_least_one_chibi(self, cleaned_data):
        if cleaned_data.get('chibis'):
            return True

        if not self.is_creating:
            survivors = set()
            for image_obj in self.all_chibis:
                field_name = u'delete_chibi_{}'.format(image_obj.id)
                if not cleaned_data.get(field_name):
                    survivors.add(image_obj.id)
            if survivors:
                return True

        return False

    def has_a_model(self, cleaned_data):
        if not self.is_creating and self.instance.model_pkg:
            return True

        if cleaned_data.get('model_pkg'):
            return True

    def clean(self):
        cleaned_data = super(CostumeForm, self).clean()

        if cleaned_data.get('i_costume_type') != models.Costume.get_i('costume_type', 'live'):
            cleaned_data['card'] = None

        if not (self.has_a_model(cleaned_data) or self.has_at_least_one_chibi(cleaned_data)):
            raise forms.ValidationError('A costume must have a model or chibis on it.')

        if cleaned_data.get('card'):
            cleaned_data['member'] = cleaned_data['card'].member
            # We'll take the card's title, so set the Costume's name to none
            cleaned_data['name'] = None
        else:
            if not cleaned_data.get('image') and cleaned_data.get('model'):
                raise forms.ValidationError('Costumes without associated cards must have a preview image.')
            if not cleaned_data.get('name'):
                raise forms.ValidationError('Costumes without associated cards must have a name.')

        return cleaned_data

    def save(self, commit=False):
        instance = super(CostumeForm, self).save(commit=False)

        instance.save()

        # Delete existing chibis
        if not self.is_creating:
            for imageObject in self.all_chibis:
                field_name = u'delete_chibi_{}'.format(imageObject.id)
                field = self.fields.get(field_name)
                if field and self.cleaned_data[field_name]:
                    imageObject.delete()

        # Upload new chibis
        for image in self.cleaned_data['chibis']:
            if isinstance(image, int):
                continue

            if instance.card:
                use_attribute = instance.card.english_attribute
            else:
                use_attribute = 'cos' # ehhh
            image.name = u'{name}-{attribute}-chibi'.format(
                name=tourldash(instance.member.name),
                attribute=use_attribute,
            )

            imageObject = models.Chibi()
            imageObject.costume = instance
            imageObject.image = image
            imageObject.save()

        return instance

    class Meta(AutoForm.Meta):
        model = models.Costume
        fields = '__all__'

class CostumeFilterForm(MagiFiltersForm):
    # Encompasses people like the dads, chispa... etc.
    # since only the 25 main girls get real Member entries.
    ID_OF_MISC_MEMBERS = 0

    search_fields = [
        'name', 'd_names', 'card__japanese_name', 'card__name',
        'member__name', 'member__japanese_name', 'member__d_names',
    ]
    search_fields_labels = {
        'card__japanese_name': '', 'card__name': '',
        'member__japanese_name': '', 'member__d_names': '',
        'member__name': _('Member'),
    }

    presets = OrderedDict([
        ('{}-stars'.format(_rarity), {
            'verbose_name': _verbose_name,
            'fields': {
                'i_rarity': _rarity,
            },
            'image': 'star_trained.png' if _rarity in models.Card.TRAINABLE_RARITIES else 'star_untrained.png',
        }) for _rarity, _verbose_name in dict(models.Card.RARITY_CHOICES).items()
    ] + [
        (_band_name, {
            'verbose_name': _band_name,
            'fields': {
                'i_band': _i_band,
            },
            'image': u'mini_band/{}.png'.format(_band_name),
        }) for _i_band, _band_name in i_choices(models.Member.BAND_CHOICES)
    ] + [
        (_name, {
            'verbose_name': _name,
            'fields': {
                'member': _id,
            },
            'image': _image,
        }) for (_id, _name, _image) in getattr(django_settings, 'FAVORITE_CHARACTERS', [])
    ])

    i_band = forms.ChoiceField(choices=BLANK_CHOICE_DASH + i_choices(models.Member.BAND_CHOICES), label=_('Band'), required=False)
    i_band_filter = MagiFilter(selector='member__i_band')

    i_rarity = forms.ChoiceField(choices=BLANK_CHOICE_DASH + list(models.Card.RARITY_CHOICES), label=_('Rarity'), required=False)
    i_rarity_filter = MagiFilter(selector='card__i_rarity')

    version =  forms.ChoiceField(choices=BLANK_CHOICE_DASH + models.Account.VERSION_CHOICES, label=_('Server availability'))
    version_filter = MagiFilter(to_queryset=lambda form, queryset, request, value: queryset.filter(Q(card__c_versions__contains=u'"{}"'.format(value)) | Q(card__isnull=True)))

    def _member_to_queryset(self, queryset, request, value):
        i = int(value)

        if i == self.ID_OF_MISC_MEMBERS:
            return queryset.filter(member__isnull=True)
        else:
            return queryset.filter(member__id=value)

    member = forms.ChoiceField(choices=BLANK_CHOICE_DASH + [(id, full_name) for (id, full_name, image) in getattr(django_settings, 'FAVORITE_CHARACTERS', [])] +
        [(ID_OF_MISC_MEMBERS, _('Other'))], initial=None, label=_('Member'))
    member_filter = MagiFilter(to_queryset=_member_to_queryset)

    class Meta(MagiFiltersForm.Meta):
        model = models.Costume
        fields = ('view', 'search', 'i_costume_type', 'member', 'i_band', 'i_rarity', 'version')

############################################################
# Single page form

class TeamBuilderForm(MagiFiltersForm):
    account = forms.ModelChoiceField(queryset=models.Account.objects.all(), empty_label=None)

    i_band = forms.ChoiceField(choices=BLANK_CHOICE_DASH + i_choices(models.Member.BAND_CHOICES), label=_('Band'), required=False)
    i_band_filter = MagiFilter(noop=True)

    i_attribute = forms.ChoiceField(choices=BLANK_CHOICE_DASH + models.Card.ATTRIBUTE_CHOICES, label=_('Attribute'), required=False)
    i_attribute_filter = MagiFilter(noop=True)

    i_skill_type = forms.ChoiceField(choices=BLANK_CHOICE_DASH + models.Card.SKILL_TYPE_CHOICES, label=_('Skill'), required=False)
    i_skill_type_filter = MagiFilter(noop=True)

    perfect_accuracy = forms.IntegerField(label=_('How often do you hit PERFECT notes?'), widget=forms.NumberInput(attrs={
        'type':'range', 'step': '10', 'data-show-value': 'true', 'data-show-value-suffix': '%',
    }), initial=80, required=False)
    perfect_accuracy_filter = MagiFilter(noop=True)

    def clean_perfect_accuracy(self):
        return (self.cleaned_data.get('perfect_accuracy', 80) or 0) / 100

    stamina_accuracy = forms.IntegerField(label=_('How often is your life above 900?'), widget=forms.NumberInput(attrs={
        'type':'range', 'step': '10', 'data-show-value': 'true', 'data-show-value-suffix': '%',
    }), initial=80, required=False)
    stamina_accuracy_filter = MagiFilter(noop=True)

    def clean_stamina_accuracy(self):
        return (self.cleaned_data.get('stamina_accuracy', 80) or 0) / 100

    total_cards = forms.ChoiceField(required=False, label=_('Cards'), initial=5, choices=[
        (5, 5), (10, 10), (15, 15),
    ])
    total_cards_filter = MagiFilter(noop=True)

    def __init__(self, *args, **kwargs):
        super(TeamBuilderForm, self).__init__(*args, **kwargs)
        # If the user doesn't have an account, redirect to create account
        if len(getAccountIdsFromSession(self.request)) == 0:
            raise HttpRedirectException('/accounts/add/?next=/teambuilder/')
        # If the user has one account, hide the account selector
        elif len(getAccountIdsFromSession(self.request)) == 1:
            self.fields['account'] = HiddenModelChoiceField(queryset=self.fields['account'].queryset)
            self.fields['account'].initial = getAccountIdsFromSession(self.request)[0]
        # Otherwise, keep the selector but limit to the accounts owned by the authenticated user
        else:
            self.fields['account'].queryset = models.Account.objects.filter(owner=self.request.user)

    class Meta(MagiFiltersForm.Meta):
        model = models.CollectibleCard
        fields = ('account', 'i_band', 'i_attribute', 'i_skill_type')
        all_optional = False
