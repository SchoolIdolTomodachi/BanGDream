# -*- coding: utf-8 -*-
from __future__ import division
import datetime, time
from collections import OrderedDict
from django.utils.translation import ugettext_lazy as _, pgettext_lazy, string_concat, get_language
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.db.models import Q, Prefetch
from django.db import models
from django.conf import settings as django_settings
from magi.models import User, uploadItem
from magi.abstract_models import AccountAsOwnerModel, BaseAccount
from magi.item_model import BaseMagiModel, MagiModel, get_image_url_from_path, get_http_image_url_from_path, i_choices, getInfoFromChoices
from magi.utils import (
    AttrDict,
    tourldash,
    split_data,
    join_data,
    uploadToKeepName,
    staticImageURL,
    templateVariables,
    uploadTthumb,
    uploadThumb,
    upload2x,
    uploadTiny,
    getEventStatus,
    ColorField,
    filterRealCollectiblesPerAccount,
    listUnique,
)
from bang.django_translated import t

############################################################
# Utility Models

LANGUAGES_NEED_OWN_NAME = [ l for l in django_settings.LANGUAGES if l[0] in ['ru', 'zh-hans', 'zh-hant', 'kr'] ]
LANGUAGES_NEED_OWN_NAME_KEYS = [ l[0] for l in django_settings.LANGUAGES if l[0] in ['ru', 'zh-hans', 'zh-hant', 'kr'] ]
LANGUAGES_DIFFERENT_CHARSET = [ l for l in django_settings.LANGUAGES if l[0] in ['ja', 'ru', 'zh-hans', 'zh-hant', 'kr'] ]
LANGUAGES_DIFFERENT_CHARSET_KEYS = [ l[0] for l in django_settings.LANGUAGES if l[0] in ['ja', 'ru', 'zh-hans', 'zh-hant', 'kr'] ]
ALL_ALT_LANGUAGES = [ l for l in django_settings.LANGUAGES if l[0] != 'en' ]
ALL_ALT_LANGUAGES_KEYS = [ l[0] for l in django_settings.LANGUAGES if l[0] != 'en' ]
ALT_LANGUAGES_EXCEPT_JP = [ l for l in django_settings.LANGUAGES if l[0] not in ['en', 'ja'] ]
ALT_LANGUAGES_EXCEPT_JP_KEYS = [ l[0] for l in django_settings.LANGUAGES if l[0] not in ['en', 'ja'] ]

LANGUAGES_TO_VERSIONS = {
    'en': 'EN',
    'es': 'EN',
    'zh-hans': 'TW',
    'ru': 'EN',
    'it': 'EN',
    'fr': 'EN',
    'de': 'EN',
    'pl': 'EN',
    'ja': 'JP',
    'kr': 'KR',
    'id': 'EN',
    'vi': 'EN',
    'zh-hant': 'TW',
    'pt': 'EN',
    'pt-br': 'EN',
    'tr': 'EN',
}

VERSIONS_TO_LANGUAGES = {
    'JP': 'ja',
    'EN': 'en',
    'TW': 'zh-hant',
    'KR': 'kr',
}

DREAMFES_PER_LANGUAGE = {
    'ja': u'ドリームフェスティバル',
    'kr': u'드림 페스티벌',
    'zh-hans': u'夢幻祭典轉蛋',
    'zh-hant': u'夢幻祭典轉蛋',
}

#Returns the list of displayable names from an item
def displayNames(item, field_name='name'):
    t_name = getattr(item, u't_{}'.format(field_name))
    return listUnique([
        name for name in [
            unicode(t_name) if t_name else None,
            getattr(item, field_name),
            getattr(item, u'japanese_{}'.format(field_name)),
        ] if name
    ])

def displayNameHTML(item, field_name='name', separator=u'<br>'):
    names = displayNames(item, field_name=field_name)
    if not names:
        return ''
    return mark_safe(u'<span>{}</span>{}'.format(
        names[0],
        u'{}<small class="text-muted">{}</small>'.format(
            separator,
            separator.join(names[1:])
        ) if len(names) > 1 else '',
    ))

############################################################
# Account

class Account(BaseAccount):
    friend_id = models.PositiveIntegerField(_('Friend ID'), null=True)
    center = models.ForeignKey('CollectibleCard', verbose_name=_('Center'), related_name='center_of_account', null=True, on_delete=models.SET_NULL)

    VERSIONS = OrderedDict([
        ('JP', {
            'translation': _('Japanese version'),
            'image': 'ja',
            'prefix': '',
            'code': 'ja',
            'timezone': 'Asia/Tokyo',
        }),
        ('EN', {
            'translation': _('English version'),
            'image': 'world',
            'prefix': 'english_',
            'code': 'en',
            'timezone': 'UTC',
        }),
        ('TW', {
            'translation': _('Taiwanese version'),
            'image': 'zh-hant',
            'prefix': 'taiwanese_',
            'code': 'zh-hant',
            'timezone': 'Asia/Taipei',
        }),
        ('KR', {
            'translation': _('Korean version'),
            'image': 'kr',
            'prefix': 'korean_',
            'code': 'kr',
            'timezone': 'Asia/Seoul',
        }),
    ])
    VERSION_CHOICES = [(_name, _info['translation']) for _name, _info in VERSIONS.items()]
    VERSIONS_PREFIXES = OrderedDict([(_k, _v['prefix']) for _k, _v in VERSIONS.items()])
    i_version = models.PositiveIntegerField(_('Version'), choices=i_choices(VERSION_CHOICES))
    version_image = property(getInfoFromChoices('version', VERSIONS, 'image'))
    version_image_url = property(lambda _a: staticImageURL(_a.version_image, folder=u'language', extension='png'))

    is_playground = models.BooleanField(_('Playground'), default=False, db_index=True)

    PLAY_WITH = OrderedDict([
        ('Thumbs', {
            'translation': _('Thumbs'),
            'icon': 'thumbs'
        }),
        ('Fingers', {
            'translation': _('All fingers'),
            'icon': 'fingers'
        }),
        ('Index', {
            'translation': _('Index fingers'),
            'icon': 'index'
        }),
        ('Hand', {
             'translation': _('One hand'),
            'icon': 'fingers'
        }),
        ('Other', {
            'translation': _('Other'),
            'icon': 'sausage'
        }),
    ])
    PLAY_WITH_CHOICES = [(_name, _info['translation']) for _name, _info in PLAY_WITH.items()]
    i_play_with = models.PositiveIntegerField(_('Play with'), choices=i_choices(PLAY_WITH_CHOICES), null=True)
    play_with_icon = property(getInfoFromChoices('play_with', PLAY_WITH, 'icon'))

    OS_CHOICES = (
        'Android',
        'iOs',
    )
    i_os = models.PositiveIntegerField(_('Operating System'), choices=i_choices(OS_CHOICES), null=True)
    os_icon = property(lambda _a: _a.os.lower() if _a.os else None)

    device = models.CharField(_('Device'), help_text=_('The model of your device. Example: Nexus 5, iPhone 4, iPad 2, ...'), max_length=150, null=True)
    stargems_bought = models.PositiveIntegerField(null=True)

    screenshot = models.ImageField(_('Screenshot'), help_text=_('In-game profile screenshot'), upload_to=uploadItem('account_screenshot'), null=True)
    _thumbnail_screenshot = models.ImageField(null=True, upload_to=uploadThumb('account_screenshot'))
    level_on_screenshot_upload = models.PositiveIntegerField(null=True)
    is_hidden_from_leaderboard = models.BooleanField('Hide from leaderboard', default=False, db_index=True)

    def update_cache_leaderboards(self):
        self._cache_leaderboards_last_update = timezone.now()
        if self.is_hidden_from_leaderboard or self.is_playground:
            self._cache_leaderboard = None
        else:
            self._cache_leaderboard = type(self).objects.filter(level__gt=self.level, i_version=self.i_version).exclude(
                Q(is_hidden_from_leaderboard=True) | Q(is_playground=True)).values('level').distinct().count() + 1

############################################################
# Members

class Member(MagiModel):
    collection_name = 'member'

    owner = models.ForeignKey(User, related_name='added_members')

    name = models.CharField(string_concat(_('Name')), max_length=100, unique=True)
    NAMES_CHOICES = LANGUAGES_NEED_OWN_NAME
    NAME_SOURCE_LANGUAGES = ['ja']
    d_names = models.TextField(_('Name'), null=True)

    japanese_name = models.CharField(string_concat(_('Name'), ' (', t['Japanese'], ')'), max_length=100)
    display_name = property(displayNameHTML)

    alt_name = models.CharField(string_concat(_('Name'), ' (Offstage)'), max_length=100, null=True)
    ALT_NAMES_CHOICES = LANGUAGES_NEED_OWN_NAME
    ALT_NAME_SOURCE_LANGUAGES = ['ja']
    d_alt_names = models.TextField('Offstage Name', null=True)

    japanese_alt_name = models.CharField(string_concat(_('Name'), ' (Offstage - ', t['Japanese'], ')'), max_length=100, null=True)
    display_alt_name = property(lambda _s: displayNameHTML(_s, field_name='alt_name'))
    @property
    def first_name(self):
        if get_language() == 'ja':
            return self.t_name.split(' ')[-1] + u'ちゃん'
        elif get_language() in ['zh-hans', 'zh-hant', 'kr']:
            return self.t_name.split(' ')[-1]
        return self.t_name.split(' ')[0]

    image = models.ImageField(_('Image'), upload_to=uploadItem('i'))
    _original_image = models.ImageField(null=True, upload_to=uploadTiny('i'))
    square_image = models.ImageField(_('Image'), upload_to=uploadItem('i/m'))
    _original_square_image = models.ImageField(null=True, upload_to=uploadTiny('i/m'))
    image_for_favorite_character = property(lambda _s: _s.square_image_url)

    BAND_CHOICES = (
        'Poppin\'Party',
        'Afterglow',
        'Pastel*Palettes',
        'Roselia',
        'Hello, Happy World!',
        'RAISE A SUILEN',
        'Morfonica',
    )
    i_band = models.PositiveIntegerField(_('Band'), choices=i_choices(BAND_CHOICES), null=True)
    band_image = lambda _s: staticImageURL(_s.band, folder='band', extension='png')

    school = models.CharField(_('School'), max_length=100, null=True)
    SCHOOLS_CHOICES = ALL_ALT_LANGUAGES
    d_schools = models.TextField(_('School'), null=True)

    SCHOOL_YEAR_CHOICES = (
        ('First', _('First')),
        ('Second', _('Second')),
        ('Third', _('Third')),
        ('JrThird', _('Junior Third')),
        ('JrSecond', _('Junior Second')),
    )
    i_school_year = models.PositiveIntegerField(_('School year'), choices=i_choices(SCHOOL_YEAR_CHOICES), null=True)

    classroom = models.CharField(_('Classroom'), max_length = 10, null=True)

    color = ColorField(_('Color'), null=True, blank=True)

    # TODO: separate page of voice acctresses
    romaji_CV = models.CharField(_('CV'), help_text='In romaji.', max_length=100, null=True)
    CV = models.CharField(string_concat(_('CV'), ' (', t['Japanese'], ')'), help_text='In Japanese characters.', max_length=100, null=True)

    birthday = models.DateField(_('Birthday'), null=True, help_text='The year is not used, so write whatever')

    height = models.PositiveIntegerField(_('Height'), help_text='in cm', null=True)

    food_like = models.CharField(_('Liked food'), max_length=100, null=True)
    FOOD_LIKES_CHOICES = ALL_ALT_LANGUAGES
    d_food_likes = models.TextField(_('Liked food'), null=True)

    food_dislike = models.CharField(_('Disliked food'), max_length=100, null=True)
    FOOD_DISLIKES_CHOICES = ALL_ALT_LANGUAGES
    d_food_dislikes = models.TextField(_('Disliked food'), null=True)

    ASTROLOGICAL_SIGN_CHOICES = (
        ('Leo', _('Leo')),
        ('Aries', _('Aries')),
        ('Libra', _('Libra')),
        ('Virgo', _('Virgo')),
        ('Scorpio', _('Scorpio')),
        ('Capricorn', _('Capricorn')),
        ('Pisces', _('Pisces')),
        ('Gemini', _('Gemini')),
        ('Cancer', _('Cancer')),
        ('Sagittarius', _('Sagittarius')),
        ('Aquarius', _('Aquarius')),
        ('Taurus', _('Taurus')),
    )
    i_astrological_sign = models.PositiveIntegerField(_('Astrological Sign'), choices=i_choices(ASTROLOGICAL_SIGN_CHOICES), null=True)
    @property
    def astrological_sign_image_url(self): return staticImageURL(self.i_astrological_sign, folder='i_astrological_sign', extension='png')

    instrument = models.CharField(_('Instrument'), max_length=100, null=True)
    INSTRUMENTS_CHOICES = ALL_ALT_LANGUAGES
    d_instruments = models.TextField(_('Instrument'), null=True)

    hobbies = models.CharField(_('Hobbies'), max_length=100, null=True)
    HOBBIESS_CHOICES = ALL_ALT_LANGUAGES
    d_hobbiess = models.TextField(_('Hobbies'), null=True)

    description = models.TextField(_('Description'), null=True)
    DESCRIPTIONS_CHOICES = ALL_ALT_LANGUAGES
    d_descriptions = models.TextField(_('Description'), null=True)

    ############################################################
    # Reverse relations

    reverse_related = [
        {
            'field_name': 'cards',
            'verbose_name': _('Cards'),
        },
        {
            'field_name': 'associated_costume',
            'url': 'costumes',
            'verbose_name': _('Costumes'),
        },
        {
            'field_name': 'officialarts',
            'url': 'assets',
            'verbose_name': _('Gallery'),
            'plural_verbose_name': _('Assets'),
            'filter_field_name': 'members',
        },
        {
            'field_name': 'comics',
            'url': 'assets',
            'verbose_name': _('Comics'),
            'filter_field_name': 'members',
        },
        {
            'field_name': 'stamps',
            'url': 'assets',
            'verbose_name': _('Stamps'),
            'filter_field_name': 'members',
        },
        {
            'field_name': 'fans',
            'url': 'users',
            'verbose_name': _('Fans'),
            'filter_field_name': 'favorite_character',
            'max_per_line': 8,
            'allow_ajax_per_item': False,
        },
    ]

    @property
    def fans(self):
        return User.objects.filter(
            Q(preferences__favorite_character1=self.id)
            | Q(preferences__favorite_character2=self.id)
            | Q(preferences__favorite_character3=self.id)
        ).select_related('preferences').order_by('-id')

    def _asset_queryset(self, type):
        return Asset.objects.filter(
            Q(members=self) | Q(i_band=self.i_band),
        ).filter(
            i_type=Asset.get_i('type', type),
        ).order_by('-id')

    @property
    def officialarts(self):
        return self._asset_queryset('officialart').select_related('song').prefetch_related(
            Prefetch('members', to_attr='all_members'),
        )

    @property
    def comics(self):
        queryset = self._asset_queryset('comic')
        version = LANGUAGES_TO_VERSIONS.get(get_language(), None)
        if version:
            queryset = queryset.filter(**{
                u'{}image__isnull'.format(Account.VERSIONS[version]['prefix']): False,
            }).exclude(**{
                u'{}image'.format(Account.VERSIONS[version]['prefix']): '',
            }).distinct()
        return queryset

    @property
    def stamps(self):
        return self._asset_queryset('stamp').select_related('event')

    ############################################################
    # Cache total

    _cache_total_fans_days = 1
    _cache_total_fans_last_update = models.DateTimeField(null=True)
    _cache_total_fans = models.PositiveIntegerField(null=True)

    def to_cache_total_fans(self):
        return self.fans.count()

    ############################################################
    # Birthday banner, used when latest news are generated

    @property
    def birthday_banner_url(self):
        try:
            # Latest rarest card
            return Card.objects.filter(member=self).filter(
                show_art_on_homepage=True).order_by(
                    '-i_rarity', '-release_date')[0].art_original_url
        except IndexError:
            return None

    ############################################################
    # Unicode

    def __unicode__(self):
        return unicode(self.t_name)

    ############################################################
    # Meta

    class Meta:
        ordering = ['id']

############################################################
# Card

class Card(MagiModel):
    collection_name = 'card'

    owner = models.ForeignKey(User, related_name='added_cards')
    id = models.PositiveIntegerField(_('ID'), unique=True, primary_key=True, db_index=True)
    member = models.ForeignKey(Member, verbose_name=_('Member'), related_name='cards', null=True, on_delete=models.SET_NULL, db_index=True)

    RARITY_CHOICES = (
        (1, u'★'),
        (2, u'★★'),
        (3, u'★★★'),
        (4, u'★★★★'),
    )
    RARITY_WITHOUT_I_CHOICES = True
    i_rarity = models.PositiveIntegerField(_('Rarity'), choices=RARITY_CHOICES, db_index=True)

    ATTRIBUTES = OrderedDict([
        (1, {
            'translation': _('Power'),
            'english': u'Power',
        }),
        (2, {
            'translation': _('Cool'),
            'english': u'Cool',
        }),
        (3, {
            'translation': _('Pure'),
            'english': u'Pure',
        }),
        (4, {
            'translation': _('Happy'),
            'english': u'Happy',
        }),
    ])
    ATTRIBUTE_CHOICES = [(_name, _info['translation']) for _name, _info in ATTRIBUTES.items()]
    ATTRIBUTE_WITHOUT_I_CHOICES = True
    i_attribute = models.PositiveIntegerField(_('Attribute'), choices=ATTRIBUTE_CHOICES, db_index=True)
    english_attribute = property(getInfoFromChoices('attribute', ATTRIBUTES, 'english'))

    name = models.CharField(_('Title'), max_length=100, null=True)
    NAME_SOURCE_LANGUAGES = ['ja']
    NAMES_CHOICES = ALT_LANGUAGES_EXCEPT_JP
    d_names = models.TextField(_('Title'), null=True)
    japanese_name = models.CharField(string_concat(_('Title'), ' (', t['Japanese'], ')'), max_length=100, null=True)

    VERSIONS = Account.VERSIONS
    VERSIONS_CHOICES = Account.VERSION_CHOICES
    c_versions = models.TextField(_('Server availability'), blank=True, null=True, default='"JP"')

    release_date = models.DateField(_('Release date'), null=True, db_index=True)
    is_promo = models.BooleanField(_('Promo card'), default=False)
    is_original = models.BooleanField(_('Original card'), default=False)

    # Skill info

    SKILL_TYPES = OrderedDict([
        (1, {
            'translation': _(u'Score up'),
            'english': 'Score up',
            'japanese_translation': u'スコアＵＰ',
            'icon': 'scoreup',

            # Main skill
            'variables': ['duration', 'percentage'],
            'template': _(u'For the next {duration} seconds, score of all notes boosted by +{percentage}%'),
            'special_templates': {
                'perfect_only': _(u'For the next {duration} seconds, score of PERFECT notes boosted by +{percentage}%'),
                'based_on_stamina': _(u'For the next {duration} seconds, if life is {stamina} or above, score boosted by +{percentage}%, otherwise score boosted by +{alt_percentage}%'),
                'based_on_accuracy': _(u'For the next {duration} seconds, score boosted by +{percentage}% until a {note_type} note is hit, then score boosted by +{alt_percentage}%'),
                'perfect_only_influence': _(u'For the next {duration} seconds, score of PERFECT notes boosted by +{percentage}%, or +{cond_percentage}% if your team consists of only {influence} members'),
                'based_on_accuracy_influence': _(u'For the next {duration} seconds, score boosted by +{percentage}% (+{cond_percentage}% if your team consists of only {influence} members) until a {note_type} note is hit, then score boosted by +{alt_percentage}%'),
            },
            'special_variables': {
                'perfect_only': ['duration', 'percentage'],
                'based_on_stamina': ['duration', 'stamina', 'percentage', 'alt_percentage'],
                'based_on_accuracy': ['duration', 'note_type', 'percentage', 'alt_percentage'],
                'perfect_only_influence': ['duration', 'percentage', 'influence', 'cond_percentage'],
                'based_on_accuracy_influence': ['duration', 'note_type', 'percentage', 'alt_percentage', 'influence', 'cond_percentage'],
            },
            'japanese_template': u'{duration}スコアが{percentage}％UPする',
            'special_japanese_templates': {
                'perfect_only': u'{duration}秒間PERFECTのときのみ、スコアが{percentage}% UPする',
                'based_on_stamina': u'{duration}秒間スコアが{alt_percentage}%UP、発動時に自分のライフが{stamina}以上の場合はスコアが{percentage}%UPする',
                'based_on_accuracy': u'{duration}秒間スコアが{alt_percentage}％UP、{note_type}以下を出すまではスコアが{percentage}％ UPする',
                'perfect_only_influence': u'{duration}秒間 PERFECTのときのみ、スコアが{percentage}% UP。 発動者のバンド編成が{influence}のみの場合はPERFECTのときのみ、スコアが{cond_percentage}％ UP',
                'based_on_accuracy_influence': u'{duration}秒間 スコアが{alt_percentage}％ UP、{note_type}以下を出すまではスコアが{percentage}％ UP 、発動者のバンド編成が{influence}のみの場合は{note_type}以下を出すまでスコアが{cond_percentage}% UP',
            },

            # Side skill
            'side_variables': ['duration', 'percentage'],
            'side_template': _(u'and boosts score of all notes by {percentage}% for the next {duration} seconds'),
            'side_japanese_template': u'、{duration}秒間スコアが {percentage}%UPする',
        }),
        (2, {
            'translation': _(u'Life recovery'),
            'english': 'Life recovery',
            'japanese_translation': u'ライフ回復',
            'icon': 'healer',

            # Main skill
            'variables': ['stamina'],
            'template': _(u'Restores life by {stamina}'),
            'special_templates': {
                'perfect_only': _(u'For the next {duration} seconds, score of PERFECT notes boosted by +{percentage}%'),
                'based_on_stamina': _(u'For the next {duration} seconds, if life is {stamina} or above, score boosted by +{percentage}%, otherwise restores life by {alt_stamina}'),
            },
            'special_variables': {
                'perfect_only': ['duration', 'percentage'],
                'based_on_stamina': ['stamina', 'duration', 'percentage', 'alt_stamina'],
            },
            'japanese_template': u'ライフが{stamina}回復し',
            'special_japanese_templates': {
                'perfect_only': u'{duration}秒間PERFECTのときのみ、スコアが{percentage}% UPする',
                'based_on_stamina': u'発動時に自分のライフが{stamina}以上の場合は、{duration}秒間スコアが{percentage}%UPする。ライフが{stamina}未満の場合は、ライフが{alt_stamina}回復する',
            },

            # Side skill
            'side_variables': ['stamina'],
            'side_template': _(u'and restores life by {stamina}'),
            'side_japanese_template': u'、ライフが {stamina} 回復し',
        }),
        (3, {
            'translation': _(u'Perfect lock'),
            'english': 'Perfect lock',
            'japanese_translation': u'判定強化',
            'icon': 'perfectlock',

            # Main skill
            'variables': ['note_type'],
            'template': _(u'All {note_type} notes turn into PERFECT notes'),
            'japanese_template': u'{note_type} 以上がすべてPERFECTになり',

            # Side skill
            'side_variables': ['duration', 'note_type'],
            'side_template': _(u'and turn all {note_type} notes turn into PERFECT notes for the next {duration} seconds'),
            'side_japanese_template': u'{duration}秒間{note_type}以上がすべてPERFECTになる',
        }),
        (4, {
            'translation': _(u'Life guard'),
            'english': 'Life guard',
            'japanese_translation': u'ライフ減少無効',
            'icon': 'fingers',

            # Main skill
            'variables': [],
            'template': _(u'BAD/MISS notes do not cause damage'),
            'japanese_template': u'BAD以下でもライフが減少しなくなり',

            # Side skill
            'side_variables': ['duration'],
            'side_template': _(u'and BAD/MISS notes do not cause damage for the next {duration} seconds'),
            'side_japanese_template': u'{duration}秒間BAD以下でもライフが減少しなくなり',
        }),
    ])

    SKILL_SPECIAL_CHOICES = (
        ('perfect_only', 'Based off PERFECT notes'),
        ('based_on_stamina', 'Scoreup based on stamina'),
        ('based_on_accuracy', 'Better scoreup if you can hit perfects'),
        ('perfect_only_influence', 'Based off perfects, but rewards full-band teams'),
        ('based_on_accuracy_influence', 'Better scoreup if you can hit perfects, with a band/attribute influence'),
    )

    ALL_VARIABLES = { item: True for sublist in [ _info['variables'] + _info['side_variables'] + [ii for sl in [_i for _i in _info.get('special_variables', {}).values()] for ii in sl] for _info in SKILL_TYPES.values() ] for item in sublist }.keys()
    VARIABLES_PER_SKILL_TYPES = {
        'skill': { _skill_type: _info['variables'] for _skill_type, _info in SKILL_TYPES.items() },
        'side_skill': { _skill_type: _info['side_variables'] for _skill_type, _info in SKILL_TYPES.items() },
    }

    # This function is called once to set the static SPECIAL_CASES_VARIABLES.
    # It's written like this because we can't access SKILL_SPECIAL_CHOICES from the inner dict comp
    # (I don't know why).
    def make_SPECIAL_CASES_VARIABLES(SKILL_TYPES, SKILL_SPECIAL_CHOICES):
        return {
            _skill_type: {
                _i: _info['special_variables'][_k] for _i, _k in enumerate([pair[0] for pair in SKILL_SPECIAL_CHOICES]) if _k in _info['special_variables']
            } for _skill_type, _info in SKILL_TYPES.items() if 'special_variables' in _info
        }
    SPECIAL_CASES_VARIABLES = make_SPECIAL_CASES_VARIABLES(SKILL_TYPES, SKILL_SPECIAL_CHOICES)

    TEMPLATE_PER_SKILL_TYPES = {
        'skill': { _skill_type: unicode(_info['template']) for _skill_type, _info in SKILL_TYPES.items() },
        'side_skill': { _skill_type: unicode(_info['side_template']) for _skill_type, _info in SKILL_TYPES.items() },
    }

    def make_SPECIAL_CASES_TEMPLATE(SKILL_TYPES, SKILL_SPECIAL_CHOICES):
        return {
            _skill_type: {
                _i: unicode(_info['special_templates'][_k]) for _i, _k in enumerate([_c[0] for _c in SKILL_SPECIAL_CHOICES]) if _k in _info['special_templates']
            } for _skill_type, _info in SKILL_TYPES.items() if 'special_templates' in _info
        }
    SPECIAL_CASES_TEMPLATE = make_SPECIAL_CASES_TEMPLATE(SKILL_TYPES, SKILL_SPECIAL_CHOICES)

    # Main skill

    skill_name = models.CharField(_('Skill name'), max_length=100, null=True)
    japanese_skill_name = models.CharField(string_concat(_('Skill name'), ' (', t['Japanese'], ')'), max_length=100, null=True)
    SKILL_NAME_SOURCE_LANGUAGES = ['ja']
    SKILL_NAMES_CHOICES = ALT_LANGUAGES_EXCEPT_JP
    d_skill_names = models.TextField(_('Skill name'), null=True)

    SKILL_TYPE_WITHOUT_I_CHOICES = True
    SKILL_TYPE_CHOICES = [(_name, _info['translation']) for _name, _info in SKILL_TYPES.items()]
    i_skill_type = models.PositiveIntegerField(_('Skill'), choices=SKILL_TYPE_CHOICES, null=True, db_index=True)
    japanese_skill_type = property(getInfoFromChoices('skill_type', SKILL_TYPES, 'japanese_translation'))
    skill_icon = property(getInfoFromChoices('skill_type', SKILL_TYPES, 'icon'))
    @property
    def skill_template(self):
        return self.SKILL_TYPES[self.skill_type].get('special_templates', {}).get(self.skill_special, self.SKILL_TYPES[self.skill_type]['template'])
    @property
    def japanese_skill_template(self):
        return self.SKILL_TYPES[self.skill_type].get('special_japanese_templates', {}).get(self.skill_special, self.SKILL_TYPES[self.skill_type]['japanese_template'])

    @property
    def skill_variables(self):
        return {
            key: getattr(self, u'skill_{}'.format(key))
            for key in self.SPECIAL_CASES_VARIABLES.get(self.skill_type, {}).get(self.i_skill_special, self.VARIABLES_PER_SKILL_TYPES['skill'].get(self.skill_type, []))
        }

    @property
    def skill(self):
        if self.i_skill_type is None: return None
        return self.skill_template.format(**self.skill_variables)

    @property
    def japanese_skill(self):
        if self.i_skill_type is None: return None
        return self.japanese_skill_template.format(**self.skill_variables)

    # Side skill

    SIDE_SKILL_TYPE_CHOICES = SKILL_TYPE_CHOICES
    SIDE_SKILL_TYPE_WITHOUT_I_CHOICES = True
    i_side_skill_type = models.PositiveIntegerField('Side skill', choices=SIDE_SKILL_TYPE_CHOICES, null=True, db_index=True)
    japanese_side_skill_type = property(getInfoFromChoices('side_skill_type', SKILL_TYPES, 'japanese_translation'))
    side_skill_template = property(getInfoFromChoices('side_skill_type', SKILL_TYPES, 'side_template'))
    japanese_side_skill_template = property(getInfoFromChoices('side_skill_type', SKILL_TYPES, 'side_japanese_template'))
    side_skill_icon = property(getInfoFromChoices('side_skill_type', SKILL_TYPES, 'icon'))

    @property
    def side_skill_variables(self):
        return {
            key: getattr(self, u'skill_{}'.format(key))
            for key in self.SKILL_TYPES[self.side_skill_type]['side_variables']
        }

    @property
    def side_skill(self):
        if self.i_side_skill_type is None: return None
        return self.side_skill_template.format(**self.side_skill_variables)

    @property
    def japanese_side_skill(self):
        if self.i_side_skill_type is None: return None
        return self.japanese_side_skill_template.format(**self.side_skill_variables)

    # Full skill

    @property
    def full_skill(self):
        if not self.i_skill_type: return None
        return u'{} {}'.format(
            self.skill,
            self.side_skill if self.i_side_skill_type else u'',
        )

    @property
    def japanese_full_skill(self):
        if not self.i_skill_type: return None
        return u'{} {}'.format(
            self.japanese_skill,
            self.japanese_side_skill if self.i_side_skill_type else u'',
        )

    # Skill variables

    i_skill_special = models.PositiveIntegerField('Skill details - Special case', choices=i_choices(SKILL_SPECIAL_CHOICES), null=True)

    SKILL_NOTE_TYPE_CHOICES = (
        'MISS',
        'BAD',
        'GOOD',
        'GREAT',
        'PERFECT',
    )
    i_skill_note_type = models.PositiveIntegerField('{note_type}', choices=i_choices(SKILL_NOTE_TYPE_CHOICES), null=True)
    skill_stamina = models.PositiveIntegerField('{stamina}', null=True)
    skill_alt_stamina = models.PositiveIntegerField('{alt_stamina}', null=True)
    skill_duration = models.PositiveIntegerField('{duration}', null=True, help_text='in seconds')
    skill_percentage = models.FloatField('{percentage}', null=True, help_text='0-100')
    skill_alt_percentage = models.FloatField('{alt_percentage}', null=True, help_text='0-100')
    skill_cond_percentage = models.FloatField('{cond_percentage}', null=True, help_text='0-100')

    SKILL_INFLUENCE_FIRST_BAND_ID = 501
    SKILL_INFLUENCE_CHOICES = OrderedDict(ATTRIBUTE_CHOICES + 
        [(SKILL_INFLUENCE_FIRST_BAND_ID + i, band) for i, band in enumerate(Member.BAND_CHOICES)])
    SKILL_INFLUENCE_WITHOUT_I_CHOICES = True
    i_skill_influence = models.PositiveIntegerField('{influence}', null=True, choices=SKILL_INFLUENCE_CHOICES.iteritems())

    @property
    def skill_influence(self):
        enum = self.SKILL_INFLUENCE_CHOICES.get(self.i_skill_influence)
        # Attribute names are translatable, band names are not.
        if enum and self.i_skill_influence < self.SKILL_INFLUENCE_FIRST_BAND_ID:
            return _(enum)
        
        return enum

    # Images
    image = models.ImageField(_('Icon'), upload_to=uploadItem('c'), null=True)
    _original_image = models.ImageField(null=True, upload_to=uploadTiny('c'))
    image_trained = models.ImageField(string_concat(_('Icon'), ' (', _('Trained'), ')'), upload_to=uploadItem('c/a'), null=True)
    _original_image_trained = models.ImageField(null=True, upload_to=uploadTiny('c/a'))

    tinypng_settings = {
        'art': {
            'resize': 'scale',
            'height': 402,
        },
        'art_trained': {
            'resize': 'scale',
            'height': 402,
        },
    }

    art = models.ImageField(_('Art'), upload_to=uploadItem('c/art'), null=True)
    _original_art = models.ImageField(null=True, upload_to=uploadTiny('c/art'))
    _tthumbnail_art = models.ImageField(null=True, upload_to=uploadTthumb('c/art'))
    _2x_art = models.ImageField(null=True, upload_to=upload2x('c/art'))
    show_art_on_homepage = models.BooleanField(default=True)

    art_trained = models.ImageField(string_concat(_('Art'), ' (', _('Trained'), ')'), upload_to=uploadItem('c/art/a'), null=True)
    _original_art_trained = models.ImageField(null=True, upload_to=uploadTiny('c/art/a'))
    _tthumbnail_art_trained = models.ImageField(null=True, upload_to=uploadTthumb('c/art/a'))
    _2x_art_trained = models.ImageField(null=True, upload_to=upload2x('c/art/a'))
    show_trained_art_on_homepage = models.BooleanField(default=True)

    transparent = models.ImageField(_('Transparent'), upload_to=uploadItem('c/transparent'), null=True)
    _tthumbnail_transparent = models.ImageField(null=True, upload_to=uploadTthumb('c/transparent'))
    _2x_transparent = models.ImageField(null=True, upload_to=upload2x('c/transparent'))

    transparent_trained = models.ImageField(string_concat(_('Transparent'), ' (', _('Trained'), ')'), upload_to=uploadItem('c/transparent/a'), null=True)
    _tthumbnail_transparent_trained = models.ImageField(null=True, upload_to=uploadTthumb('c/transparent/a'))
    _2x_transparent_trained = models.ImageField(null=True, upload_to=upload2x('c/transparent/a'))

    # Statistics
    performance_min = models.PositiveIntegerField(string_concat(_('Performance'), ' (', _('Minimum'), ')'), default=0)
    performance_max = models.PositiveIntegerField(string_concat(_('Performance'), ' (', _('Maximum'), ')'), default=0)
    performance_trained_max = models.PositiveIntegerField(string_concat(_('Performance'), ' (', _('Trained'), ', ', _('Maximum'), ')'), default=0)
    technique_min = models.PositiveIntegerField(string_concat(_('Technique'), ' (', _('Minimum'), ')'), default=0)
    technique_max = models.PositiveIntegerField(string_concat(_('Technique'), ' (', _('Maximum'), ')'), default=0)
    technique_trained_max = models.PositiveIntegerField(string_concat(_('Technique'), ' (', _('Trained'), ', ', _('Maximum'), ')'), default=0)
    visual_min = models.PositiveIntegerField(string_concat(_('Visual'), ' (', _('Minimum'), ')'), default=0)
    visual_max = models.PositiveIntegerField(string_concat(_('Visual'), ' (', _('Maximum'), ')'), default=0)
    visual_trained_max = models.PositiveIntegerField(string_concat(_('Visual'), ' (', _('Trained'), ', ', _('Maximum'), ')'), default=0)

    @property
    def overall_min(self):
        return self.performance_min + self.technique_min + self.visual_min
    @property
    def overall_max(self):
        return self.performance_max + self.technique_max + self.visual_max
    @property
    def overall_trained_max(self):
        return self.performance_trained_max + self.technique_trained_max + self.visual_trained_max

    # Other members that appear in the card art
    cameo_members = models.ManyToManyField(Member, related_name='cameo_members', verbose_name=_('Cameos'))

    # Tools

    TRAINABLE_RARITIES = [3, 4]

    @property
    def trainable(self):
        return self.i_rarity in self.TRAINABLE_RARITIES

    MAX_LEVELS = {
        1: 20,
        2: 30,
        3: (40, 50),
        4: (50, 60),
    }

    @property
    def max_level(self):
        return self.MAX_LEVELS[self.i_rarity][0] if self.trainable else self.MAX_LEVELS[self.i_rarity]

    @property
    def max_level_trained(self):
        return self.MAX_LEVELS[self.i_rarity][1] if self.trainable else self.MAX_LEVELS[self.i_rarity]

    @property
    def share_image(self):
        return self.art_trained or self.art

    # All Stats

    @property
    def statuses(self):
        statuses = [
            ('min', _('Level {level}').format(level=1)),
            ('max', _('Level {level}').format(level=self.max_level)),
        ]
        if self.trainable:
            statuses.append(('trained_max', _('Level {level}').format(level=self.max_level_trained)))
        return statuses

    _local_stats = None

    @property
    def stats_percent(self):
        if not self._local_stats:
            self._local_stats = [
                (status, [(
                    field,
                    localized,
                    getattr(self, field + '_' + status),
                    django_settings.MAX_STATS[field + '_max'],
                    (getattr(self, field + '_' + status) / (django_settings.MAX_STATS[field + '_' + ('trained_max' if self.trainable else 'max')] or 1)) * 100,
                ) for (field, localized) in [
                    ('performance', _('Performance')),
                    ('technique', _('Technique')),
                    ('visual', _('Visual')),
                    ('overall', _('Overall')),
                ]]) for status, localized in self.statuses
            ]
        return self._local_stats

    # Cache member

    _cache_member_days = 20
    _cache_member_last_update = models.DateTimeField(null=True)
    _cache_j_member = models.TextField(null=True)

    @classmethod
    def cached_member_pre(self, d):
        d['name'] = d['names'].get('en', None)
        d['t_name'] = d['unicode'] = d['names'].get(get_language(), d['name'])

    def to_cache_member(self):
        if not self.member:
            return {
                'id': None,
                'names': {},
                'image': None,
            }
        names = self.member.names or {}
        names['en'] = self.member.name
        names['ja'] = self.member.japanese_name
        return {
            'id': self.member_id,
            'names': names,
            'image': unicode(self.member.square_image),
        }

    # Cache events

    _cached_events_collection_name = 'event'
    _cache_events_days = 20
    _cache_events_last_update = models.DateTimeField(null=True)
    _cache_j_events = models.TextField(null=True)

    @classmethod
    def cached_events_pre(self, d):
        d['name'] = d['names'].get('en', None)
        d['japanese_name'] = d['names'].get('ja', None)
        d['t_name'] = d['unicode'] = d['names'].get(get_language(), d['name'])

    def to_cache_events(self):
        events = []
        for event in Event.objects.filter(Q(main_card_id=self.id) | Q(secondary_card_id=self.id)):
            names = event.names or {}
            names['en'] = event.name
            names['ja'] = event.japanese_name
            events.append({
                'id': event.id,
                'names': names,
                'image': unicode(event.image),
            })
        return events if events else None

    # Cache gachas

    _cached_gachas_collection_name = 'gacha'
    _cache_gachas_days = 20
    _cache_gachas_last_update = models.DateTimeField(null=True)
    _cache_j_gachas = models.TextField(null=True)

    @classmethod
    def cached_gachas_pre(self, d):
        d['name'] = d['names'].get('en', None)
        d['japanese_name'] = d['names'].get('ja', None)
        d['t_name'] = d['unicode'] = d['names'].get(get_language(), d['name'])

    def to_cache_gachas(self):
        gachas = []
        for gacha in Gacha.objects.filter(cards__id=self.id):
            names = gacha.names or {}
            names['en'] = gacha.name
            names['ja'] = gacha.japanese_name
            gachas.append({
                'id': gacha.id,
                'names': names,
                'image': unicode(gacha.image),
            })
        return gachas if gachas else None

    # Cache cameos

    _cached_cameos_collection_name = 'member'
    _cache_cameos_days = 200
    _cache_cameos_last_update = models.DateTimeField(null=True)
    _cache_j_cameos = models.TextField(null=True)

    def to_cache_cameos(self):
        return [{
            'id': cameo.id,
            'name': unicode(cameo.name),
            'japanese_name': unicode(cameo.japanese_name),
            'image': unicode(cameo.square_image),
        } for cameo in self.cameo_members.all()]

    @classmethod
    def cached_cameos_pre(self, d):
        d['unicode'] = d['japanese_name'] if get_language() == 'ja' else d['name']
        return d


    ############################################################
    # Reverse relations

    reverse_related = (
        ('favorited', 'favoritecards', lambda: _('Favorite {things}').format(things=_('Cards').lower())),
        ('collectedcards', 'collectiblecards', lambda: _('Collected {things}').format(things=_('Cards').lower())),
    )

    ############################################################
    # Cache totals

    _cache_total_favorited_days = 1
    _cache_total_favorited_last_update = models.DateTimeField(null=True)
    _cache_total_favorited = models.PositiveIntegerField(null=True)

    def to_cache_total_favorited(self):
        return self.favorited.all().count()

    _cache_total_collectedcards_days = 1
    _cache_total_collectedcards_last_update = models.DateTimeField(null=True)
    _cache_total_collectedcards = models.PositiveIntegerField(null=True)

    def to_cache_total_collectedcards(self):
        return filterRealCollectiblesPerAccount(self.collectedcards.all()).count()

    ########

    @property # To allow favorite card to use the same template
    def card(self):
        return self

    ############################################################
    # Unicode

    def __unicode__(self):
        if self.id:
            return u'{rarity} {member_name} - {attribute}{name}'.format(
                rarity=self.t_rarity,
                member_name=self.cached_member.t_name if self.cached_member else '',
                attribute=self.t_attribute,
                name=u' - {}'.format(self.t_name) if self.t_name else '',
            )
        return u''

    ############################################################
    # Meta

    class Meta:
        ordering = ['-release_date', '-id']

############################################################
# Collectible Cards

class CollectibleCard(AccountAsOwnerModel):
    collection_name = 'collectiblecard'

    account = models.ForeignKey(Account, verbose_name=_('Account'), related_name='cardscollectors')
    card = models.ForeignKey(Card, verbose_name=_('Card'), related_name='collectedcards')
    trained = models.BooleanField(_('Trained'), default=False)
    prefer_untrained = models.BooleanField(_('Prefer untrained card image'), default=False)
    max_leveled = models.NullBooleanField(_('Max level'))
    first_episode = models.NullBooleanField(_('{nth} episode').format(nth=_('1st')))
    memorial_episode = models.NullBooleanField(_('Memorial episode'))
    skill_level = models.PositiveIntegerField(_('Skill level'), null=True, blank=True, validators=[
        MinValueValidator(1),
        MaxValueValidator(5),
    ])

    @property
    def image(self):
        return self.card.image_trained if self.trained and not self.prefer_untrained else self.card.image

    @property
    def image_url(self):
        return self.card.image_trained_url if self.trained and not self.prefer_untrained else self.card.image_url

    @property
    def http_image_url(self):
        return self.card.http_image_trained_url if self.trained and not self.prefer_untrained else self.card.http_image_url

    @property
    def art(self):
        return self.card.art_trained if self.trained and not self.prefer_untrained else self.card.art

    @property
    def art_url(self):
        return self.card.art_trained_url if self.trained and not self.prefer_untrained else self.card.art_url

    @property
    def http_art_url(self):
        return self.card.http_art_trained_url if self.trained and not self.prefer_untrained else self.card.http_art_url

    @property
    def art_url_original(self):
        return self.card.art_trained_original_url if self.trained and not self.prefer_untrained else self.card.art_original_url

    @property
    def color(self):
        return self.card.english_attribute

    @property
    def full_skill(self):
        if self.card.skill_duration:
            self.previous_duration = self.card.skill_duration
            self.card.skill_duration = self.card.skill_duration + (((self.skill_level or 1) - 1) * 0.5)
        full_skill = unicode(self.card.full_skill)
        if self.card.skill_duration:
            self.card.skill_duration = self.previous_duration
        return full_skill

    def __unicode__(self):
        if self.id:
            return unicode(self.card)
        return super(CollectibleCard, self).__unicode__()

    class Meta:
        ordering = ['-card__i_rarity', '-trained', '-card__release_date']

class FavoriteCard(MagiModel):
    collection_name = 'favoritecard'

    owner = models.ForeignKey(User, related_name='favorite_cards')
    card = models.ForeignKey(Card, verbose_name=_('Card'), related_name='favorited')

    class Meta:
        unique_together = (('owner', 'card'), )
        ordering = ['-id']

############################################################
# Events

def _event_gacha_top_image(item, image_name='image'):
    image = None
    # Check for current event and return banner of current if any
    for prefix in Account.VERSIONS_PREFIXES.values():
        status = getattr(item, u'{}status'.format(prefix))
        if status and status != 'ended':
            image = getattr(item, u'{}{}_url'.format(prefix, image_name))
            break
    # Otherwise, return banner that makes more sense for the language the users uses
    if not image and get_language() in LANGUAGES_TO_VERSIONS:
        image = getattr(item, u'{}{}_url'.format(Account.VERSIONS_PREFIXES[LANGUAGES_TO_VERSIONS[get_language()]], image_name))
    # Otherwise, fallback to first image that exists
    if not image:
        for version in Account.VERSIONS.values():
            image = getattr(item, u'{}{}_url'.format(version['prefix'], image_name))
            if image:
                break
    # Return image or default banner
    return image or staticImageURL('bannercomingsoon.png')

class Event(MagiModel):
    collection_name = 'event'

    owner = models.ForeignKey(User, related_name='added_events')

    image = models.ImageField(_('Image'), upload_to=uploadItem('e'), null=True)
    _original_image = models.ImageField(null=True, upload_to=uploadTiny('e'))
    top_image = property(_event_gacha_top_image)

    name = models.CharField(_('Title'), max_length=100, unique=True)
    japanese_name = models.CharField(string_concat(_('Title'), ' (', t['Japanese'], ')'), max_length=100, unique=True)
    NAMES_CHOICES = ALT_LANGUAGES_EXCEPT_JP
    NAME_SOURCE_LANGUAGES = ['ja']
    d_names = models.TextField(_('Title'), null=True)

    TYPE_CHOICES = (
        ('normal', _('Normal')),
        ('challenge_live', _('Challenge Live')),
        ('vs_live', _('VS Live')),
        ('live_goals', _('Live Goals')),
        ('mission_live', _('Mission Live')),
    )
    i_type = models.PositiveIntegerField(_('Event type'), choices=i_choices(TYPE_CHOICES), default=0)

    SONG_RANKING_TYPES = [
        'challenge_live',
        'vs_live',
    ]
    GOAL_MASTER_TYPES = [
        'live_goals',
    ]

    start_date = models.DateTimeField(string_concat(_('Japanese version'), ' - ', _('Beginning')), null=True)
    end_date = models.DateTimeField(string_concat(_('Japanese version'), ' - ',_('End')), null=True)

    TIMES_PER_VERSIONS = {
        'JP': ((6, 0), (11, 59)),
        'EN': ((1, 0), (6, 59)),
        'TW': ((7, 0), (12, 59)),
        'KR': ((6, 0), (13, 0)),
    }
    FIELDS_PER_VERSION = ['image', 'countdown', 'start_date', 'end_date', 'leaderboard', 'rerun']

    MAX_RANK_WITHOUT_SS = {
        'JP': 10000,
        'EN': 1000,
        'TW': 100,
        'KR': 1000,
    }
    # Assets (stamps, titles) are added dynamically to the js variable because multiple can be present

    VERSIONS = Account.VERSIONS
    VERSIONS_CHOICES = Account.VERSION_CHOICES
    c_versions = models.TextField(_('Server availability'), blank=True, null=True, default='"JP"')

    english_image = models.ImageField(string_concat(_('English version'), ' - ', _('Image')), upload_to=uploadItem('e/e'), null=True)
    _original_english_image = models.ImageField(null=True, upload_to=uploadTiny('e/e'))
    english_start_date = models.DateTimeField(string_concat(_('English version'), ' - ', _('Beginning')), null=True)
    english_end_date = models.DateTimeField(string_concat(_('English version'), ' - ', _('End')), null=True)

    taiwanese_image = models.ImageField(string_concat(_('Taiwanese version'), ' - ', _('Image')), upload_to=uploadItem('e/t'),  null=True)
    _original_taiwanese_image = models.ImageField(null=True, upload_to=uploadTiny('e/t'))
    taiwanese_start_date = models.DateTimeField(string_concat(_('Taiwanese version'), ' - ', _('Beginning')), null=True)
    taiwanese_end_date = models.DateTimeField(string_concat(_('Taiwanese version'), ' - ', _('End')), null=True)

    korean_image = models.ImageField(string_concat(_('Korean version'), ' - ', _('Image')), upload_to=uploadItem('e/t'),  null=True)
    _original_korean_image = models.ImageField(null=True, upload_to=uploadTiny('e/t'))
    korean_start_date = models.DateTimeField(string_concat(_('Korean version'), ' - ', _('Beginning')), null=True)
    korean_end_date = models.DateTimeField(string_concat(_('Korean version'), ' - ', _('End')), null=True)

    MAIN_CARD_ALLOWED_RARITIES = (3,)
    SECONDARY_CARD_ALLOWED_RARITIES = (3, 2)

    main_card = models.ForeignKey(Card, related_name='main_card_event', null=True, limit_choices_to={
        'i_rarity__in': MAIN_CARD_ALLOWED_RARITIES,
    }, on_delete=models.SET_NULL)
    secondary_card = models.ForeignKey(Card, related_name='secondary_card_event', null=True, limit_choices_to={
        'i_rarity__in': SECONDARY_CARD_ALLOWED_RARITIES,
    }, on_delete=models.SET_NULL)

    BOOST_ATTRIBUTE_CHOICES = Card.ATTRIBUTE_CHOICES
    BOOST_ATTRIBUTE_WITHOUT_I_CHOICES = True
    i_boost_attribute = models.PositiveIntegerField(_('Boost attribute'), choices=BOOST_ATTRIBUTE_CHOICES, null=True)
    english_boost_attribute = property(getInfoFromChoices('boost_attribute', Card.ATTRIBUTES, 'english'))

    BOOST_STAT_CHOICES = (
        ('performance', _('Performance')),
        ('technique', _('Technique')),
        ('visual', _('Visual')),
    )
    i_boost_stat = models.PositiveIntegerField(_('Boost statistic'), choices=i_choices(BOOST_STAT_CHOICES), null=True)

    boost_members = models.ManyToManyField(Member, related_name='boost_in_events', verbose_name=_('Boost members'))

    @property
    def cached_gacha(self):
        # No need for a cache because the gacha is select_related in item view
        self.gacha.unicode = unicode(self.gacha)
        return self.gacha

    def get_status(self, version='JP'):
        start_date = getattr(self, u'{}start_date'.format(Account.VERSIONS_PREFIXES[version]))
        end_date = getattr(self, u'{}end_date'.format(Account.VERSIONS_PREFIXES[version]))
        return getEventStatus(start_date, end_date)

    status = property(lambda _s: _s.get_status())
    english_status = property(lambda _s: _s.get_status(version='EN'))
    taiwanese_status = property(lambda _s: _s.get_status(version='TW'))
    korean_status = property(lambda _s: _s.get_status(version='KR'))

    # Cache totals

    reverse_related = (
        ('participations', 'eventparticipations', _('Participated events')),
    )

    _cache_total_participations_days = 1
    _cache_total_participations_last_update = models.DateTimeField(null=True)
    _cache_total_participations = models.PositiveIntegerField(null=True)

    def to_cache_total_participations(self):
        return filterRealCollectiblesPerAccount(self.participations.all()).count()

    ############################################################
    # Unicode

    def __unicode__(self):
        return self.t_name

    ############################################################
    # Meta

    class Meta:
        ordering = ['-start_date']

############################################################
# Collectible Event

class EventParticipation(AccountAsOwnerModel):
    collection_name = 'eventparticipation'

    account = models.ForeignKey(Account, verbose_name=_('Account'), related_name='events')
    event = models.ForeignKey(Event, verbose_name=_('Event'), related_name='participations')

    score = models.PositiveIntegerField(_('Score'), null=True)
    ranking = models.PositiveIntegerField(_('Ranking'), null=True)

    song_score = models.PositiveIntegerField(_('Song score'), null=True)
    song_ranking = models.PositiveIntegerField(_('Song ranking'), null=True)

    is_goal_master = models.NullBooleanField(_('Goal Master'))
    is_ex_goal_master = models.NullBooleanField(_('EX Goal Master'))

    screenshot = models.ImageField(_('Screenshot'), upload_to=uploadItem('event_screenshot'), null=True)
    _thumbnail_screenshot = models.ImageField(null=True, upload_to=uploadThumb('event_screenshot'))

    @property
    def ranking_image_url(self):
        return get_image_url_from_path(u'static/img/badges/medal{}.png'.format(4 - self.ranking))

    @property
    def leaderboard_details(self):
        return [(k, v) for k, v in [
            ('score', {
                'icon': 'scoreup',
                'verbose_name': _('Score'),
                'value': self.score,
            }),
            ('song_score', {
                'icon': 'song',
                'verbose_name': _('Song score'),
                'value': self.song_score,
            }),
            ('song_ranking', {
                'icon': 'contest',
                'verbose_name': _('Song ranking'),
                'value': self.song_ranking,
            }),
            ('is_goal_master', {
                'icon': 'achievement',
                'verbose_name': _('Goal Master'),
                'value': self.is_goal_master,
            }),
            ('is_ex_goal_master', {
                'icon': 'achievement',
                'verbose_name': _('EX Goal Master'),
                'value': self.is_ex_goal_master,
            }),
        ] if v['value'] and not (
            (k in ['song_score', 'song_ranking'] and self.event.type not in Event.SONG_RANKING_TYPES)
            and (k in ['is_goal_master', 'is_ex_goal_master']
                 and self.event.type not in Event.GOAL_MASTER_TYPES)
        )]

    def to_cache_account(self):
        d = super(EventParticipation, self).to_cache_account()
        d['i_version'] = self.account.i_version
        return d

    @property
    def image(self):
        return getattr(self.event, u'{}image'.format(Account.VERSIONS_PREFIXES[self.cached_account.version])) or self.event.image

    @property
    def image_url(self):
        return getattr(self.event, u'{}image_url'.format(Account.VERSIONS_PREFIXES[self.cached_account.version])) or self.event.image_url

    @property
    def http_image_url(self):
        return getattr(self.event, u'http_{}image_url'.format(Account.VERSIONS_PREFIXES[self.cached_account.version])) or self.event.http_image_url

    ############################################################
    # Unicode

    def __unicode__(self):
        if self.id:
            return unicode(self.event)
        return super(EventParticipation, self).__unicode__()

    ############################################################
    # Meta

    class Meta:
        ordering = ['-event__start_date']

############################################################
# Song

class Song(MagiModel):
    collection_name = 'song'

    DIFFICULTY_VALIDATORS = [
        MinValueValidator(1),
        MaxValueValidator(50),
    ]

    DIFFICULTIES = [
        ('easy', _('Easy')),
        ('normal', _('Normal')),
        ('hard', _('Hard')),
        ('expert', _('Expert')),
        ('special', _('Special')),
    ]

    SONGWRITERS_DETAILS = [
        ('composer', _('Composer')),
        ('lyricist', _('Lyricist')),
        ('arranger', _('Arranger')),
    ]

    owner = models.ForeignKey(User, related_name='added_songs')
    image = models.ImageField('Album cover', upload_to=uploadItem('s'))
    _original_image = models.ImageField(null=True, upload_to=uploadTiny('s'))

    BAND_CHOICES = list(Member.BAND_CHOICES) + ['Glitter*Green', 'Special Band']
    i_band = models.PositiveIntegerField(_('Band'), choices=i_choices(BAND_CHOICES))

    special_band = models.CharField(_('Band'), max_length=100, null=True)
    SPECIAL_BANDS_CHOICES = LANGUAGES_DIFFERENT_CHARSET
    d_special_bands = models.TextField(_('Band'), null=True)

    japanese_name = models.CharField(_('Title'), max_length=100, unique=True)
    romaji_name = models.CharField(string_concat(_('Title'), ' (', _('Romaji'), ')'), max_length=100, null=True)
    name = models.CharField(string_concat(_('Title'), ' (', _('Translation'), ')'), max_length=100, null=True)
    NAMES_CHOICES = ALT_LANGUAGES_EXCEPT_JP
    NAME_SOURCE_LANGUAGES = ['ja']
    d_names = models.TextField(_('Title'), null=True)

    VERSIONS = Account.VERSIONS
    VERSIONS_CHOICES = Account.VERSION_CHOICES
    c_versions = models.TextField(_('Server availability'), blank=True, null=True, default='"JP"')

    itunes_id = models.PositiveIntegerField(_('Preview'), help_text='iTunes ID', null=True)
    length = models.PositiveIntegerField(_('Length'), null=True)

    @property
    def length_in_minutes(self):
        return time.strftime('%M:%S', time.gmtime(self.length))

    is_cover = models.BooleanField(_('Cover song'), default=False)
    is_full = models.BooleanField('FULL', default=False)
    bpm = models.PositiveIntegerField(_('Beats per minute'), null=True)
    release_date = models.DateField(_('Release date'), null=True)

    composer = models.CharField(_('Composer'), max_length=100, null=True)
    lyricist = models.CharField(_('Lyricist'), max_length=100, null=True)
    arranger = models.CharField(_('Arranger'), max_length=100, null=True)

    easy_notes = models.PositiveIntegerField(string_concat(_('Easy'), ' - ', _('Notes')), null=True)
    easy_difficulty = models.PositiveIntegerField(string_concat(_('Easy'), ' - ', _('Difficulty')), validators=DIFFICULTY_VALIDATORS, null=True)
    normal_notes = models.PositiveIntegerField(string_concat(_('Normal'), ' - ', _('Notes')), null=True)
    normal_difficulty = models.PositiveIntegerField(string_concat(_('Normal'), ' - ', _('Difficulty')), validators=DIFFICULTY_VALIDATORS, null=True)
    hard_notes = models.PositiveIntegerField(string_concat(_('Hard'), ' - ', _('Notes')), null=True)
    hard_difficulty = models.PositiveIntegerField(string_concat(_('Hard'), ' - ', _('Difficulty')), validators=DIFFICULTY_VALIDATORS, null=True)
    expert_notes = models.PositiveIntegerField(string_concat(_('Expert'), ' - ', _('Notes')), null=True)
    expert_difficulty = models.PositiveIntegerField(string_concat(_('Expert'), ' - ', _('Difficulty')), validators=DIFFICULTY_VALIDATORS, null=True)
    special_notes = models.PositiveIntegerField(string_concat(_('Special'), ' - ', _('Notes')), null=True)
    special_difficulty = models.PositiveIntegerField(string_concat(_('Special'), ' - ', _('Difficulty')), validators=DIFFICULTY_VALIDATORS, null=True)
    sp_notes = models.BooleanField(_('{} notes').format('SP'), default=False)

    UNLOCK = OrderedDict([
        ('gift', {
            'translation': _('Gift'),
            'template': string_concat(_('Gift'), ' ({occasion})'),
            'variables': ['occasion'],
        }),
        ('purchase', {
            'translation': _('Purchase at CiRCLE'),
            'template': _('Purchase at CiRCLE'),
            'variables': [],
        }),
        ('complete_story', {
            'translation': _('Complete story'),
            'template': _('Complete {story_type} story, chapter {chapter}'),
            'variables': ['story_type', 'chapter'],
        }),
        ('complete_tutorial', {
            'translation': _('Complete Tutorial'),
            'template': _('Complete Tutorial'),
            'variables': [],
        }),
        ('initial', {
            'translation': _('Initially available'),
            'template': _('Initially available'),
            'variables': [],
        }),
        ('event', {
            'translation': _('Event gift'),
            'template': _('Event gift'),
            'variables': [],
        }),
        ('level', {
            'translation': _('Level'),
            'template': _('Level {level}'),
            'variables': ['level'],
        }),
        ('level_band', {
            'translation': string_concat(_('Level'), ' / ', _('Band')),
            'template': string_concat('{band} - ', _('Level {level}')),
            'variables': ['level', 'band'],
            'variables_transform': {
                'band': lambda _s, _v: Member.get_verbose_i('band', int(_v)),
            },
        }),
        ('other', {
            'translation': _('Other'),
            'template': '{how_to_unlock}',
            'variables': ['how_to_unlock'],
        }),
    ])

    UNLOCK_CHOICES = [(_name, _info['translation']) for _name, _info in UNLOCK.items()]
    i_unlock = models.PositiveIntegerField(_('How to unlock?'), choices=i_choices(UNLOCK_CHOICES))

    c_unlock_variables = models.CharField(_('How to unlock?'), max_length=100, null=True)
    unlock_variables_keys = property(getInfoFromChoices('unlock', UNLOCK, 'variables'))
    unlock_variables_transform = property(getInfoFromChoices('unlock', UNLOCK, 'variables_transform'))
    unlock_template = property(getInfoFromChoices('unlock', UNLOCK, 'template'))
    @property
    def unlock_sentence(self):
        return unicode(self.unlock_template).format(**{
            k: (self.unlock_variables_transform or {}).get(k, lambda s, v: v)(self, v)
            for k, v in zip(self.unlock_variables_keys, self.unlock_variables)
        })

    event = models.ForeignKey(Event, verbose_name=_('Event'), related_name='gift_songs', null=True, on_delete=models.SET_NULL)

    @property
    def cached_event(self):
        # No need for a cache because the event is select_related in item view
        self.event.unicode = unicode(self.event)
        return self.event

    @property # Needed to use with types in magicollections
    def type(self):
        return self.unlock

    # Cache totals

    reverse_related = (
        ('played', 'playedsongs', _('Played songs')),
    )

    _cache_total_played_days = 1
    _cache_total_played_last_update = models.DateTimeField(null=True)
    _cache_total_played = models.PositiveIntegerField(null=True)

    def to_cache_total_played(self):
        return filterRealCollectiblesPerAccount(self.playedby.all()).count()

    ############################################################
    # Unicode

    def __unicode__(self):
        if get_language() == 'ja':
            return self.japanese_name
        if not self.romaji_name:
            return self.t_name or self.japanese_name
        if get_language() == 'en' and self.name:
            if self.name != self.romaji_name:
                return u'{} ({})'.format(
                    self.romaji_name,
                    self.name,
                )
        elif self.names.get(get_language(), None):
            if self.t_name != self.romaji_name:
                return u'{} ({})'.format(
                    self.romaji_name,
                    self.t_name,
                )
        return self.romaji_name

    ############################################################
    # Meta

    class Meta:
        ordering = ['-release_date']

############################################################
# Collectible Song

class PlayedSong(AccountAsOwnerModel):
    collection_name = 'playedsong'

    account = models.ForeignKey(Account, verbose_name=_('Account'), related_name='playedsong')
    song = models.ForeignKey(Song, verbose_name=_('Song'), related_name='playedby')

    DIFFICULTY_CHOICES = (
        ('easy', _('Easy')),
        ('normal', _('Normal')),
        ('hard', _('Hard')),
        ('expert', _('Expert')),
        ('special', _('Special')),
    )

    i_difficulty = models.PositiveIntegerField(_('Difficulty'), choices=i_choices(DIFFICULTY_CHOICES), default=0)
    difficulty_image_url = property(lambda _ps: staticImageURL(_ps.difficulty, folder=u'songs', extension='png'))

    score = models.PositiveIntegerField(_('Score'), null=True)
    full_combo = models.NullBooleanField(_('Full combo'))
    all_perfect = models.NullBooleanField(_('All perfect'))

    screenshot = models.ImageField(_('Screenshot'), upload_to=uploadItem('song_screenshot'), null=True)
    _thumbnail_screenshot = models.ImageField(null=True, upload_to=uploadThumb('song_screenshot'))

    @property
    def image(self):
        return self.song.image

    @property
    def image_url(self):
        return self.song.image_url

    @property
    def http_image_url(self):
        return self.song.http_image_url

    @property
    def leaderboard_details(self):
        return [(k, v) for k, v in [
            ('score', {
                'icon': 'scoreup',
                'verbose_name': _('Score'),
                'value': self.score,
            }),
            ('full_combo', {
                'icon': 'combo',
                'verbose_name': _('Full combo'),
                'value': self.full_combo,
            }),
            ('all_perfect', {
                'icon': 'combo',
                'verbose_name': _('All perfect'),
                'value': self.all_perfect,
            }),
        ] if v['value']]

    ############################################################
    # Unicode

    def __unicode__(self):
        if self.id:
            return unicode(self.song)
        return super(PlayedSong, self).__unicode__()

    ############################################################
    # Meta

    class Meta:
        ordering = ['song__expert_difficulty', 'song_id', '-i_difficulty']

############################################################
# Gacha

class Gacha(MagiModel):
    collection_name = 'gacha'

    owner = models.ForeignKey(User, related_name='added_gacha')

    image = models.ImageField(_('Image'), upload_to=uploadItem('g'), null=True)
    _original_image = models.ImageField(null=True, upload_to=uploadTiny('g'))
    top_image = property(_event_gacha_top_image)

    name = models.CharField(_('Title'), max_length=100, unique=True)
    japanese_name = models.CharField(string_concat(_('Title'), ' (', t['Japanese'], ')'), max_length=100, unique=True)
    NAMES_CHOICES = ALT_LANGUAGES_EXCEPT_JP
    NAME_SOURCE_LANGUAGES = ['ja']
    d_names = models.TextField(_('Title'), null=True)

    limited = models.BooleanField(_('Limited'), default=False)
    dreamfes = models.BooleanField(default=False)

    start_date = models.DateTimeField(_('Beginning'), null=True)
    end_date = models.DateTimeField(_('End'), null=True)

    english_image = models.ImageField(string_concat(_('English version'), ' - ', _('Image')), upload_to=uploadItem('e/e'), null=True)
    _original_english_image = models.ImageField(null=True, upload_to=uploadTiny('e/e'))
    english_start_date = models.DateTimeField(string_concat(_('English version'), ' - ', _('Beginning')), null=True)
    english_end_date = models.DateTimeField(string_concat(_('English version'), ' - ', _('End')), null=True)

    taiwanese_image = models.ImageField(string_concat(_('Taiwanese version'), ' - ', _('Image')), upload_to=uploadItem('e/t'), null=True)
    _original_taiwanese_image = models.ImageField(null=True, upload_to=uploadTiny('e/t'))
    taiwanese_start_date = models.DateTimeField(string_concat(_('Taiwanese version'), ' - ', _('Beginning')), null=True)
    taiwanese_end_date = models.DateTimeField(string_concat(_('Taiwanese version'), ' - ', _('End')), null=True)

    korean_image = models.ImageField(string_concat(_('Korean version'), ' - ', _('Image')), upload_to=uploadItem('e/t'), null=True)
    _original_korean_image = models.ImageField(null=True, upload_to=uploadTiny('e/t'))
    korean_start_date = models.DateTimeField(string_concat(_('Korean version'), ' - ', _('Beginning')), null=True)
    korean_end_date = models.DateTimeField(string_concat(_('Korean version'), ' - ', _('End')), null=True)

    ATTRIBUTE_CHOICES = Card.ATTRIBUTE_CHOICES
    ATTRIBUTE_WITHOUT_I_CHOICES = True
    i_attribute = models.PositiveIntegerField(_('Attribute'), choices=ATTRIBUTE_CHOICES, null=True)
    english_attribute = property(getInfoFromChoices('attribute', Card.ATTRIBUTES, 'english'))

    event = models.ForeignKey(Event, verbose_name=_('Event'), related_name='gachas', null=True, on_delete=models.SET_NULL)
    cards = models.ManyToManyField(Card, verbose_name=('Cards'), related_name='gachas')

    TIMES_PER_VERSIONS = {
        'JP': ((6, 0), (5, 59)),
        'EN': ((1, 0), (0, 59)),
        'TW': ((7, 0), (6, 59)),
        'KR': ((6, 0), (6, 0)),
    }
    FIELDS_PER_VERSION = ['image', 'countdown', 'start_date', 'end_date', 'rerun']

    GACHA_TYPES = [
        ('permanent', _(u'Permanent')),
        ('limited', _(u'Limited')),
        ('dreamfes', 'Dream festival'),
    ]

    VERSIONS = Account.VERSIONS
    VERSIONS_CHOICES = Account.VERSION_CHOICES
    c_versions = models.TextField(_('Server availability'), blank=True, null=True, default='"JP"')

    @property
    def cached_event(self):
        # No need for a cache because the event is select_related in item view
        self.event.unicode = unicode(self.event)
        return self.event

    def get_status(self, version='JP'):
        start_date = getattr(self, u'{}start_date'.format(Account.VERSIONS_PREFIXES[version]))
        end_date = getattr(self, u'{}end_date'.format(Account.VERSIONS_PREFIXES[version]))
        return getEventStatus(start_date, end_date)

    status = property(lambda _s: _s.get_status())
    english_status = property(lambda _s: _s.get_status(version='EN'))
    taiwanese_status = property(lambda _s: _s.get_status(version='TW'))
    korean_status = property(lambda _s: _s.get_status(version='KR'))

    ############################################################
    # Unicode

    def __unicode__(self):
        return _('{} Gacha').format(self.t_name)

    ############################################################
    # Meta

    class Meta:
        ordering = ['-start_date']


############################################################
# Rerun gacha event

class Rerun(MagiModel):
    collection_name = 'rerun'

    event = models.ForeignKey(Event, verbose_name=_('Event'), related_name='reruns', null=True)
    gacha = models.ForeignKey(Gacha, verbose_name=_('Gacha'), related_name='reruns', null=True)

    ITEMS = ['event', 'gacha']
    ITEMS_MODELS = { 'event': Event, 'gacha': Gacha }

    fk_as_owner = 'event__owner'

    @property
    def owner(self):
        return getattr(self.event, 'owner', None) or getattr(self.gacha, 'owner', None)

    @property
    def owner_id(self):
        return getattr(self.event, 'owner_id', None) or getattr(self.gacha, 'owner_id', None)

    VERSIONS = Account.VERSIONS
    VERSION_CHOICES = Account.VERSION_CHOICES
    i_version = models.PositiveIntegerField(_('Version'), choices=i_choices(VERSION_CHOICES))
    version_timezone = property(getInfoFromChoices('version', VERSIONS, 'timezone'))
    version_prefix = property(getInfoFromChoices('version', VERSIONS, 'prefix'))

    start_date = models.DateTimeField(_('Beginning'))
    end_date = models.DateTimeField(_('End'))

    @property
    def status(self):
        return getEventStatus(self.start_date, self.end_date)

    def __unicode__(self):
        return u'Rerun {} "{}" ({}): {} - {}'.format(
            'Gacha' if self.gacha_id else 'Event',
            self.gacha or self.event,
            self.version,
            self.start_date,
            self.end_date,
        )

############################################################
# Item

class Item(MagiModel):
    collection_name = 'item'
    owner = models.ForeignKey(User, related_name='added_items')

    image = models.ImageField(_('Image'), upload_to=uploadItem('items'))
    _original_image = models.ImageField(null=True, upload_to=uploadTiny('items'))

    name = models.CharField(_('Title'), max_length=100, null=True, help_text='plural')
    NAMES_CHOICES = ALL_ALT_LANGUAGES
    d_names = models.TextField(_('Title'), null=True)

    TYPE_CHOICES = [
        ('main', _('Main')),
        ('boost', _('Live boost')),
        ('ticket', _('Studio ticket')),
        ('other', _('Other')),
    ]
    i_type = models.PositiveIntegerField(_('Type'), choices=i_choices(TYPE_CHOICES), null=True)

    m_description = models.TextField(_('Description'), null=True)
    M_DESCRIPTIONS_CHOICES = ALL_ALT_LANGUAGES
    d_m_descriptions = models.TextField(_('Description'), null=True)

    def __unicode__(self):
        return self.t_name

    class Meta:
        ordering = ['id']

############################################################
# Collected item

class CollectibleItem(AccountAsOwnerModel):
    collection_name = 'collectibleitem'

    account = models.ForeignKey(Account, verbose_name=_('Account'), related_name='items')
    item = models.ForeignKey(Item, verbose_name=_('Item'), related_name='collectedby')
    quantity = models.PositiveIntegerField(_('Quantity'), default=1)

    image = property(lambda _s: _s.item.image)
    image_url = property(lambda _s: _s.item.image_url)
    http_image_url = property(lambda _s: _s.item.http_image_url)

    @property
    def subtitle(self):
        return u'x{}'.format(self.quantity)

    def __unicode__(self):
        if self.id:
            return unicode(self.item)
        return super(CollectibleItem, self).__unicode__()

############################################################
# Area item

class Area(MagiModel):
    collection_name = 'area'

    owner = models.ForeignKey(User, related_name='added_areas')

    image = models.ImageField(_('Image'), upload_to=uploadItem('areas'))
    _original_image = models.ImageField(null=True, upload_to=uploadTiny('areas'))

    name = models.CharField(_('Title'), max_length=100)
    NAMES_CHOICES = ALL_ALT_LANGUAGES
    d_names = models.TextField(_('Title'), null=True)

    def __unicode__(self):
        return self.t_name

class AreaItem(MagiModel):
    collection_name = 'areaitem'
    owner = models.ForeignKey(User, related_name='added_area_items')

    image = models.ImageField(_('Image'), upload_to=uploadItem('areas/items'))
    _original_image = models.ImageField(null=True, upload_to=uploadTiny('areas/items'))

    name = models.CharField(_('Title'), max_length=100, null=True)
    NAMES_CHOICES = ALL_ALT_LANGUAGES
    d_names = models.TextField(_('Title'), null=True)

    area = models.ForeignKey(Area, verbose_name=_('Location'), null=True, on_delete=models.SET_NULL)

    TYPE_CHOICES = [
        ('studio', _('Studio')),
        ('poster', _('Poster')),
        ('counter', _('Counter')),
        ('minitable', _('Mini table')),
        ('magazine', _('Magazine rack')),
        ('entrance', _('Entrance')),
        ('sign', _('Sign')),
        ('plaza', _('Plaza')),
        ('garden', _('Garden')),
        ('special', _('Specials menu')),
    ]
    i_type = models.PositiveIntegerField(_('Area'), choices=i_choices(TYPE_CHOICES), null=True)

    INSTRUMENT_CHOICES = [
        ('mic', _('Mic')),
        ('guitar', _('Guitar')),
        ('bass', _('Bass')),
        ('drum', _('Drums')),
        ('other', _('Other')),
    ]
    i_instrument = models.PositiveIntegerField(_('Instrument'), choices=i_choices(INSTRUMENT_CHOICES), null=True)

    member = models.ForeignKey(Member, verbose_name=_('Member'), related_name='area_items',
        help_text='Unless instrument, just choose member in affected band', null=True, on_delete=models.SET_NULL)

    ATTRIBUTE_CHOICES = Card.ATTRIBUTE_CHOICES
    ATTRIBUTE_WITHOUT_I_CHOICES = True
    i_attribute = models.PositiveIntegerField(_('Attribute'), choices=ATTRIBUTE_CHOICES, null=True)

    STAT_CHOICES = (
        ('performance', _('Performance')),
        ('technique', _('Technique')),
        ('visual', _('Visual')),
    )
    i_boost_stat = models.PositiveIntegerField(_('Statistic'), choices=i_choices(STAT_CHOICES), null=True)

    max_level = models.PositiveIntegerField(_('Max level'), default=5)

    values = models.CharField(max_length=100, null=True, help_text='Seperate with spaces in ascending order')
    is_percent = models.BooleanField('Values are %?', default=True)
    lifes = models.CharField(max_length=100, null=True, help_text='Seperate with spaces in ascending order')

    about = models.TextField(_('About'), null=True)
    ABOUTS_CHOICES = ALL_ALT_LANGUAGES
    d_abouts = models.TextField(_('About'), null=True)

    @property
    def value_list(self):
        return None if not self.values else list(float(i) for i in self.values.split())

    @property
    def life_list(self):
        return None if not self.lifes else list(float(i) for i in self.lifes.split())

    @property
    def i_band(self):
        return self.member.band

    @property
    def formatted_name(self):
        # Mics with names (ex: "Idol Mic")
        if self.instrument == 'mic' and self.t_name:
            return _('{name} {thing}').format(name=self.t_name, thing=_('Mic'))
        # Other instruments (ex: "Michelle's keyboard")
        elif self.instrument == 'other' and self.member and self.t_name:
            return _('{name}\'s {thing}').format(name=self.member.first_name, thing=self.t_name)
        # Member's instruments (ex: "Hina's Guitar")
        elif self.instrument and self.member:
            return _('{name}\'s {thing}').format(name=self.member.first_name, thing=self.t_instrument)
        # Flyers, posters, etc (ex: "Afterglow Poster")
        elif self.member and self.t_name:
            return _('{name} {thing}').format(name=self.member.t_band, thing=self.t_name)
        # Other (ex: "Fountain")
        elif self.t_name:
            return self.t_name
        return _('Area item')

    @property
    def affected(self):
        if self.t_attribute and self.member:
            return u'{} / {}'.format(self.t_attribute, self.member.t_band)
        elif self.t_attribute:
            return self.t_attribute
        elif self.member:
            return self.member.t_band
        return _('All')

    @property
    def stat(self):
        if self.i_boost_stat is not None:
            return unicode(self.t_boost_stat)
        return unicode(_('All'))

    def formatted_description(self, level=1):
        if level > len(self.value_list or ''):
            value = '???'
        else:
            value = self.value_list[level-1]
        if self.is_percent:
            value = string_concat(value, '%')
        if level > len(self.life_list or ''):
            life = '???'
        else:
            life = self.life_list[level-1]
        if self.life_list:
            return _('Restores life by {life} and {affected} members get a {value} boost on {stat} statistics').format(
                life=life, affected=self.affected, value=value, stat=self.stat)
        return _('{affected} members get a {value} boost on {stat} statistics').format(
            affected=self.affected, value=value, stat=self.stat)

    def __unicode__(self):
        return self.formatted_name

############################################################
# Collected item

class CollectibleAreaItem(AccountAsOwnerModel):
    collection_name = 'collectibleareaitem'

    account = models.ForeignKey(Account, verbose_name=_('Account'), related_name='areaitems')
    areaitem = models.ForeignKey(AreaItem, verbose_name=_('Area item'), related_name='collectedby')
    level = models.PositiveIntegerField(_('Level'), default=1)

    image = property(lambda _s: _s.areaitem.image)
    image_url = property(lambda _s: _s.areaitem.image_url)
    http_image_url = property(lambda _s: _s.areaitem.http_image_url)
    formatted_name = property(lambda _s: _s.areaitem.formatted_name)

    @property
    def formatted_description(self):
        return self.areaitem.formatted_description(level=self.level)

    @property
    def subtitle(self):
        return _('Level {level}').format(level=self.level)

    def __unicode__(self):
        if self.id:
            return unicode(self.areaitem)
        return super(CollectibleAreaItem, self).__unicode__()

############################################################
# Assets

class Asset(MagiModel):
    collection_name = 'asset'

    owner = models.ForeignKey(User, related_name='added_assets')

    image = models.ImageField(_('Image'), upload_to=uploadItem('asset'), null=True)
    _tthumbnail_image = models.ImageField(null=True, upload_to=uploadTthumb('asset'))

    english_image = models.ImageField(string_concat(_('English version'), ' - ', _('Image')), upload_to=uploadItem('asset/e'), null=True)
    _tthumbnail_english_image = models.ImageField(null=True, upload_to=uploadTthumb('asset/e'))

    taiwanese_image = models.ImageField(string_concat(_('Taiwanese version'), ' - ', _('Image')), upload_to=uploadItem('asset/t'),  null=True)
    _tthumbnail_taiwanese_image = models.ImageField(null=True, upload_to=uploadTthumb('asset/t'))

    korean_image = models.ImageField(string_concat(_('Korean version'), ' - ', _('Image')), upload_to=uploadItem('asset/k'),  null=True)
    _tthumbnail_korean_image = models.ImageField(null=True, upload_to=uploadTthumb('asset/k'))

    def _get_top_image(self, thumbnail):
        show_image_version = 'EN'

        # Get preferred version of image from user's language
        if get_language() in LANGUAGES_TO_VERSIONS:
            show_image_version = LANGUAGES_TO_VERSIONS[get_language()]

        # Get preferred version of image from filtered choice
        if self.request:
            try:
                show_image_version = Account.get_reverse_i(
                    'version', int(self.request.GET.get('i_version', None)),
                ) or show_image_version
            except (KeyError, ValueError, TypeError):
                pass

        # Get thumbnail of image from preferred version
        image = getattr(self, u'{prefix}image{thumbnail}_url'.format(
            prefix=Account.VERSIONS[show_image_version]['prefix'],
            thumbnail='_thumbnail' if thumbnail else '',
        ), None)

        # Fallback to first image that exists
        if not image:
            for version in Account.VERSIONS.values():
                version_image = getattr(self, u'{prefix}image{thumbnail}_url'.format(
                    prefix=version['prefix'],
                    thumbnail='_thumbnail' if thumbnail else '',
                ), None)
                if version_image:
                    image = version_image
                    break

        return image or staticImageURL('stars.png')

    top_image = property(lambda _s: _s._get_top_image(thumbnail=False))
    top_image_list = property(lambda _s: _s._get_top_image(thumbnail=True))

    VARIABLES = ['name', 'i_band', 'members', 'c_tags', 'event', 'value', 'source', 'source_link', 'song']

    TYPES = OrderedDict([
        # Keys can't contain a dash
        ('comic', {
            'translation': _('Comics'),
            'variables': ['name', 'i_band', 'members', 'value'],
            'to_unicode': lambda _a: _a.t_name or _('Comics'),
            'icon': 'album',
        }),
        ('background', {
            'translation': _('Backgrounds'),
            'variables': ['name', 'i_band', 'c_tags'],
            'icon': 'pictures',
            'to_unicode': lambda _a: u'{}{}'.format(
                _a.t_name or _('Background'),
                u' ({})'.format(_a.band) if _a.band else '',
            ),
        }),
        ('stamp', {
            'translation': _('Stamps'),
            'variables': ['name', 'members', 'event'],
            'image': 'stamp.png',
            'to_unicode': lambda _a: u'{event} {name}'.format(
                event=_a.event if _a.event else '',
                name=((_a.t_name if not _a.event else u'“{name}”'.format(name=_a.t_name))
                      if _a.name else (_('Stamps') if not _a.event else _('Rare stamp'))),
            ),
        }),
        ('title', {
            'translation': _('Titles'),
            'variables': ['name', 'members', 'event', 'song', 'value'],
            'icon': 'list',
            'to_unicode': lambda _a: u'{event}{song}{name}'.format(
                event=_a.event if _a.event else '',
                song=u'{dash}{song}'.format(
                    dash=u' - ' if _a.event else '',
                    song=_a.song) if _a.song else '',
                name=u'{dash}{name}{value}'.format(
                    dash=u' - ' if _a.event or _a.song else '',
                    name=_a.t_name if _a.name else '',
                    value=_a.formatted_title_value,
                ) if _a.name or _a.value else '',
            ),
        }),
        ('interface', {
            'translation': _('Interface'),
            'variables': ['name'],
            'to_unicode': lambda _a: _a.t_name or _('Interface'),
            'icon': 'icons-list',
        }),
        ('officialart', {
            'translation': _('Official art'),
            'variables': ['name', 'i_band', 'members', 'song', 'c_tags', 'source', 'source_link', 'value'],
            'icon': 'pictures',
            'to_unicode': lambda _a: (
                _a.t_name
                or _a.song
                or _a.band
                or u', '.join([member.t_name for member in getattr(_a, 'all_members', [])])
                or _('Official art')
            ),
            'navbar_link_list': 'bangdream',
        }),
    ])
    TYPE_CHOICES = [(_name, _info['translation']) for _name, _info in TYPES.items()]
    i_type = models.PositiveIntegerField('Type', choices=i_choices(TYPE_CHOICES), null=True)
    type_variables = property(getInfoFromChoices('type', TYPES, 'variables'))
    type_per_line = property(getInfoFromChoices('type', TYPES, 'per_line'))
    to_unicode = property(getInfoFromChoices('type', TYPES, 'to_unicode'))
    type_image = property(getInfoFromChoices('type', TYPES, 'image'))
    type_icon = 'pictures'

    name = models.CharField(_('Title'), max_length=100, null=True)
    NAMES_CHOICES = ALL_ALT_LANGUAGES
    NAME_SOURCE_LANGUAGES = ['ja']
    d_names = models.TextField(_('Title'), null=True)

    BAND_CHOICES = Member.BAND_CHOICES
    i_band = models.PositiveIntegerField(_('Band'), choices=i_choices(BAND_CHOICES), null=True, help_text='Tagging a band is a shortcut to tagging all the members, so you don\'t need to tag the members when you tag a band.')

    members = models.ManyToManyField(Member, related_name='assets', verbose_name=_('Members'), null=True)

    BACKGROUND_TAGS = (
        ('outdoor', _('Outdoor')),
        ('indoor', _('Indoor')),
        ('school', _('School')),
        ('stage', _('Stage')),
        ('home', _('Home')),
        ('date', _('Dating spot')),
        ('seasonal', _('Seasonal')),
        ('sunset', _('Sunset')),
        ('night', _('Night')),
        ('rain', _('Rain')),
        ('snow', _('Snow')),
        ('sakura', _('Cherry blossoms')),
        ('fireworks', _('Fireworks')),
    )
    OFFICIAL_TAGS = (
        ('transparent', _('Transparent')),
        ('login', _('Login')),
        ('twitter', 'Twitter'),
        ('bluray', 'Blu-ray'),
        ('cd', _('Album cover')),
        ('collab', _('Collab')),
        ('dengeki', _('Dengeki G\'s magazine')),
        ('seasonal', _('Seasonal')),
        ('birthday', _('Birthday')),
        ('live', _('Live')),
    )
    TAGS_CHOICES = BACKGROUND_TAGS + OFFICIAL_TAGS
    c_tags = models.TextField(_('Tags'), null=True)

    event = models.ForeignKey(Event, verbose_name=_('Event'), related_name='assets', null=True, on_delete=models.SET_NULL)
    song = models.ForeignKey(Song, verbose_name=_('Song'), related_name='assets', null=True, on_delete=models.SET_NULL)

    source = models.CharField(_('Source'), max_length=100, null=True)
    source_link = models.CharField(max_length=100, null=True)

    value = models.PositiveIntegerField(null=True)

    @property
    def tinypng_settings(self):
        # Don't generate thumbnails for titles + stamps, just use TinyPNG to compress (hacky)
        if self.type in ['title', 'stamp']:
            return {
                '_tthumbnail_{}image'.format(version_prefix): {
                    'resize': None,
                } for version_prefix in Account.VERSIONS_PREFIXES.values()
            }
        return {}

    @property
    def item_url(self):
        item_url = MagiModel.item_url.fget(self)
        if self.request and self.request.GET.get('i_version', None):
            return u'{}?i_version={}'.format(
                item_url,
                self.request.GET['i_version'],
            )
        return item_url

    @property
    def ajax_item_url(self):
        item_url = MagiModel.ajax_item_url.fget(self)
        if self.request and self.request.GET.get('i_version', None):
            return u'{}?i_version={}'.format(
                item_url,
                self.request.GET['i_version'],
            )
        return item_url

    @property
    def formatted_title_value(self):
        if not self.value:
            return ''

        fmt = u'{space}#{value}'
        # Currently 1-3 get unique titles but we might as well make it 10.
        if self.event and self.value >= 10:
            # Both JP/EN/(TW?) use "top" literally so we don't need
            # to localize this.
            fmt = u'{space}TOP {value}'
        return fmt.format(space=' ' if self.name else '',
            value=self.value)

    def __unicode__(self):
        return unicode(self.to_unicode(self))

############################################################
# Costume

class Chibi(BaseMagiModel):
    image = models.ImageField(upload_to=uploadItem('cos/chibi'))
    _original_image = models.ImageField(upload_to=uploadTiny('cos/chibi'), null=True)
    costume = models.ForeignKey('Costume', verbose_name=_('Costume'), related_name='owned_chibis', on_delete=models.CASCADE)

    tinypng_settings = {
        'image': {
            'resize': 'scale',
            'height': 200,
        },
    }

    def __unicode__(self):
        return unicode(self.image)

class Costume(MagiModel):
    collection_name = 'costume'
    owner = models.ForeignKey(User, related_name='added_costume')

    COSTUME_TYPE_CHOICES = OrderedDict([
        # Costumes that can be used in lives. Usually associated with cards but
        # they aren't always (e.g. Year of the Dog)
        ('live', _('Live')),
        # Never associated with cards.
        ('other', _('Other')),
    ])
    i_costume_type = models.PositiveIntegerField(_('Costume type'), choices=i_choices(COSTUME_TYPE_CHOICES))

    # Basically whatever you want. If there's a card associated with a model, we'll use the
    # card's title instead.
    name = models.CharField(_('Title'), max_length=250, null=True)
    NAMES_CHOICES = ALL_ALT_LANGUAGES
    NAME_SOURCE_LANGUAGES = ['ja']
    d_names = models.TextField(_('Title'), null=True)

    @property
    def t_name(self):
        # If we're a card costume, take that card's title so we don't have to save/TL duplicate strings.
        # The form will make sure self.name is null.
        if self.card:
            return self.card.t_name or self.card.japanese_name
        return MagiModel.t_name.fget(self)

    image = models.ImageField(_('Image'), upload_to=uploadItem('cos/p'), null=True)
    _tthumbnail_image = models.ImageField(null=True, upload_to=uploadTthumb('cos/z'))
    model_pkg = models.FileField(pgettext_lazy('BanPa model viewer', 'Model'), upload_to=uploadItem('cos/z'), null=True)

    @property
    def display_image(self):
        if self.image:
            return self.image_url
        elif self.card:
            for try_img in ['transparent_trained_url', 'transparent_url']:
                g = getattr(self.card, try_img, None)
                if g:
                    return g
        return None

    @property
    def display_image_thumbnail_url(self):
        if self.image:
            return self.image_thumbnail_url
        elif self.card:
            for try_img in ['transparent_trained_thumbnail_url', 'transparent_thumbnail_url']:
                g = getattr(self.card, try_img, None)
                if g:
                    return g
        return None

    # there's nothing stopping you from associating a costume with a card whose member is
    # different, but it's weird so keep it in sync elsewhere (forms.py)
    # additionally, this is nullable just in case we want to upload NPC costumes.
    member = models.ForeignKey(Member, verbose_name=_('Member'), related_name='associated_costume', null=True, on_delete=models.CASCADE)
    card = models.OneToOneField(Card, verbose_name=_('Card'), related_name='associated_costume', null=True, on_delete=models.SET_NULL)
    # owned_chibis

    def __unicode__(self):
        return u'{}{}'.format(
            u'{} - '.format(self.member.t_name) if self.member_id else '',
            self.t_name,
        )

    class Meta:
        ordering = ['-id']

    # Cache chibis

    # _cache_chibis_days = 200
    # _cache_chibis_last_update = models.DateTimeField(null=True)
    # _cache_chibis_ids = models.TextField(null=True)
    # _cache_chibis_paths = models.TextField(null=True)

    # def update_cache_chibis(self, chibis=None):
    #     self._cache_chibis_last_update = timezone.now()
    #     if not chibis:
    #         chibis = Chibi.objects.filter(costume=self)
    #     self._cache_chibis_ids = join_data(*[ image.id for image in chibis ])
    #     self._cache_chibis_paths = join_data(*[ unicode(image) for image in chibis ])

    # def force_cache_chibis(self):
    #     self.update_cache_chibis()
    #     self.save()

    # @property
    # def cached_chibis(self):
    #     if not self._cache_chibis_last_update or self._cache_chibis_last_update < timezone.now() - datetime.timedelta(days=self._cache_chibis_days):
    #         self.force_cache_chibis()
    #     if not self._cache_chibis_ids:
    #         return []
    #     return [AttrDict({
    #         'id': id,
    #         'pk': id,
    #         'image': path,
    #         'image_url': get_image_url_from_path(path),
    #         'http_image_url': get_http_image_url_from_path(path),
    #     }) for id, path in zip(split_data(self._cache_chibis_ids), split_data(self._cache_chibis_paths))]
