# -*- coding: utf-8 -*-
import math, simplejson, random
from itertools import chain
from collections import OrderedDict
from django.conf import settings as django_settings
from django.utils.translation import ugettext_lazy as _, string_concat, get_language
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Prefetch, Q
from django.db.models.fields import BLANK_CHOICE_DASH
from magi.magicollections import (
    MainItemCollection,
    AccountCollection as _AccountCollection,
    ActivityCollection as _ActivityCollection,
    BadgeCollection as _BadgeCollection,
    DonateCollection as _DonateCollection,
    UserCollection as _UserCollection,
    StaffConfigurationCollection as _StaffConfigurationCollection,
    PrizeCollection as _PrizeCollection,
)
from magi.utils import (
    setSubField,
    CuteFormType,
    CuteFormTransform,
    torfc2822,
    custom_item_template,
    staticImageURL,
    justReturn,
    toCountDown,
    translationURL,
    AttrDict,
    mergedFieldCuteForm,
    tourldash,
    getCharacterImageFromPk,
)
from magi.default_settings import RAW_CONTEXT
from magi.item_model import i_choices
from magi.models import Activity, Notification
from magi.forms import get_account_simple_form
from bang.constants import LIVE2D_JS_FILES
from magi import settings
from bang.django_translated import t
from bang.utils import (
    rarity_to_stars_images,
    generateDifficulty,
    add_rerun_buttons,
    add_rerun_fields,
    memberBandMergeCuteForm,
    subtitledImageLink,
    bandField,
)
from bang import models, forms

############################################################
# Default MagiCircles Collections

############################################################
# User Collection

class UserCollection(_UserCollection):
    class ItemView(_UserCollection.ItemView):

        def get_meta_links(self, user, *args, **kwargs):
            first_links, meta_links, links = super(UserCollection.ItemView, self).get_meta_links(user, *args, **kwargs)
            if user.preferences.extra.get('i_favorite_band', None):
                i_band = user.preferences.extra.get('i_favorite_band')
                band = models.Song.get_reverse_i('band', int(user.preferences.extra['i_favorite_band']))
                meta_links.insert(0, AttrDict({
                    'name': 'i_favorite_band',
                    'verbose_name': _('Favorite {thing}').format(thing=_('Band').lower()),
                    'value': band,
                    'raw_value': i_band,
                    'image': staticImageURL(band, folder='mini_band',  extension='png'),
                    'url': (
                        u'/members/{}/'.format(tourldash(band))
                        if band in models.Member.BAND_CHOICES
                        else '/songs/{}/'.format(tourldash(band))
                    ),
                }))
            return (first_links, meta_links, links)

        def extra_context(self, context):
            super(UserCollection.ItemView, self).extra_context(context)
            if 'profile_birthday' in context['corner_popups']:
                context['corner_popups']['profile_birthday']['image_overflow'] = True
                context['corner_popups']['profile_birthday']['image'] = staticImageURL('birthday_kanae.png')

    class ListView(_UserCollection.ListView):
        filter_form = forms.UserFilterForm

############################################################
# Account Collection

class AccountCollection(_AccountCollection):
    form_class = forms.AccountForm
    navbar_link_list = 'community'

    _colors_images = [_c[0] for _c in settings.USER_COLORS]
    _version_images = [_c['image'] for _c in models.Account.VERSIONS.values()]
    _play_with_icons = [_c['icon'] for _c in models.Account.PLAY_WITH.values()]
    filter_cuteform = _AccountCollection.filter_cuteform.copy()
    filter_cuteform.update({
        'i_color': {
            'to_cuteform': lambda k, v: AccountCollection._colors_images.index(k) + 1,
            'image_folder': 'i_attribute',
            'transform': CuteFormTransform.ImagePath,
        },
        'has_friend_id': {
            'type': CuteFormType.OnlyNone,
        },
        'center': {
            'to_cuteform': lambda k, v: v.image_url,
            'title': _('Center'),
            'extra_settings': {
                'modal': 'true',
                'modal-text': 'true',
            },
        },
        'i_version': {
            'to_cuteform': lambda k, v: AccountCollection._version_images[k],
            'image_folder': 'language',
            'transform': CuteFormTransform.ImagePath,
        },
        'i_play_with': {
            'to_cuteform': lambda k, v: AccountCollection._play_with_icons[k],
            'transform': CuteFormTransform.FlaticonWithText,
        },
        'i_os': {
            'to_cuteform': lambda k, v: models.Account.OS_CHOICES[k].lower(),
            'transform': CuteFormTransform.FlaticonWithText,
        },
    })

    @property
    def report_edit_templates(self):
        templates = _AccountCollection.report_edit_templates.fget(self)
        templates['Incorrect version'] = 'You appear to have selected the wrong version for this account, so we edited it.'
        templates['Incorrect friend ID'] = 'You don\'t seem to be the owner of the account associated with this friend ID in game, so we edited it. Feel free to contact us with a proof and we won\'t edit it again.'
        templates['Unrealistic star gems bought'] = 'Your total number of star gems bought has been reported as being unrealistic so we edited it. Feel free to contact us with a proof and we won\'t edit it again.'
        return templates

    def to_fields(self, view, item, exclude_fields=None, *args, **kwargs):
        if exclude_fields is None: exclude_fields = []
        exclude_fields.append('owner')
        fields = super(AccountCollection, self).to_fields(view, item, *args, icons={
            'play_with': item.play_with_icon,
            'os': item.os_icon,
            'device': item.os_icon or 'id',
        }, images={
            'version': item.version_image_url,
            'stargems_bought': staticImageURL(u'stargems_bought.png'),
        }, exclude_fields=exclude_fields, **kwargs)
        setSubField(fields, 'stargems_bought', key='verbose_name', value=_('Total {item} bought').format(item=_('Star gems').lower()))
        setSubField(fields, 'stargems_bought', key='type', value='text_annotation')
        spent_yen = int(item.stargems_bought * django_settings.PRICE_PER_STARGEM) if item.stargems_bought else 0
        spent_dollars = int(spent_yen * django_settings.YEN_TO_USD)
        setSubField(fields, 'stargems_bought', key='annotation', value=_(u'~{}円 spent (~${})').format(spent_yen, spent_dollars))
        return fields

    share_image = justReturn('screenshots/leaderboard.png')

    class ListView(_AccountCollection.ListView):
        filter_form = forms.AccountFilterForm

        def buttons_per_item(self, request, context, item):
            buttons = super(AccountCollection.ListView, self).buttons_per_item(request, context, item)
            buttons['version'] = {
                'show': True, 'has_permissions': True, 'image': u'language/{}'.format(item.version_image),
                'title': item.t_version, 'url': u'{}?i_version={}'.format(
                    self.collection.get_list_url(),
                    item.i_version,
                ), 'classes': [],
            }
            return buttons

    class AddView(_AccountCollection.AddView):
        back_to_list_button = False
        simpler_form = get_account_simple_form(forms.AccountForm, simple_fields=[
            'nickname', 'i_version', 'level', 'friend_id',
        ])

        def redirect_after_add(self, request, item, ajax):
            if not ajax:
                return '/cards/?get_started&add_to_collectiblecard={account_id}&view=icons&version={account_version}&ordering=i_rarity&reverse_order=on'.format(
                    account_id=item.id,
                    account_version=item.version,
                )
            return super(AccountCollection.AddView, self).redirect_after_add(request, item, ajax)

############################################################
# Badge Collection

class BadgeCollection(_BadgeCollection):
    enabled = True

############################################################
# Prize Collection

class PrizeCollection(_PrizeCollection):
    enabled = True

############################################################
# Staff Configuration Collection

class StaffConfigurationCollection(_StaffConfigurationCollection):
    enabled = True

############################################################
# Donate Collection

class DonateCollection(_DonateCollection):
    enabled = True
    navbar_link_list = 'community'
    navbar_link_list_divider_after = True

############################################################
# Activity Collection

class ActivityCollection(_ActivityCollection):
    navbar_link = True
    navbar_link_list = 'community'

    class ListView(_ActivityCollection.ListView):
        def top_buttons(self, request, context):
            buttons = super(ActivityCollection.ListView, self).top_buttons(request, context)
            if request.user.is_authenticated():
                top_tab = (
                    'this_week' if context['filter_form'].active_tab == 'top_this_week'
                    else ('all_time' if 'from_tab' in request.GET else None
                    ))
                if top_tab:
                    buttons['other_top'] = {
                        'show': True,
                        'has_permissions': True,
                        'classes': [
                            cls for cls in self.top_buttons_classes if cls != 'btn-main'
                        ] + ['btn-secondary'],
                        'title': string_concat(
                            _('TOP'), ' - ',
                            _('This week') if top_tab == 'this_week' else _('All time'),
                        ),
                        'subtitle': _('Open {thing}').format(thing=string_concat(
                            _('TOP'), ' - ',
                            _('All time') if top_tab == 'this_week' else _('This week'),
                        )),
                        'url': (
                            '/?ordering=_cache_total_likes%2Ccreation&reverse_order=on&from_tab'
                            if top_tab == 'this_week'
                            else '/activities/top_this_week/'
                        ),
                        'icon': 'trophy',
                    }
            return buttons

############################################################
############################################################
############################################################

############################################################
# Member Collection

MEMBERS_ICONS = {
    'name': 'id',
    'alt_name': 'id',
    'band': 'rock',
    'school': 'school',
    'school_year': 'education',
    'classroom': 'school',
    'CV': 'voice-actress',
    'romaji_CV': 'voice-actress',
    'birthday': 'birthday',
    'color': 'palette',
    'height': 'measurements',
    'food_like': 'food-like',
    'food_dislike': 'food-dislike',
    'instrument': 'guitar',
    'hobbies': 'hobbies',
    'description': 'id',
    'cards': 'album',
    'fans': 'heart',
    'associated_costume': 'dress',
    'officialarts': 'pictures',
    'comics': 'album',
}

class MemberCollection(MainItemCollection):
    queryset = models.Member.objects.all()
    title = _('Member')
    plural_title = _('Members')
    icon = 'idol'
    navbar_link_list = 'bangdream'
    translated_fields = ('name', 'alt_name', 'school', 'food_like', 'food_dislike', 'instrument', 'hobbies', 'description', )

    form_class = forms.MemberForm

    def to_fields(self, view, item, extra_fields=None, exclude_fields=None, *args, **kwargs):
        if exclude_fields is None: exclude_fields = []
        if extra_fields is None: extra_fields = []
        exclude_fields += ['japanese_name', 'japanese_alt_name']
        if item.school is not None:
            exclude_fields.append('classroom')
        fields = super(MemberCollection, self).to_fields(view, item, *args, icons=MEMBERS_ICONS, images={
            'astrological_sign': staticImageURL(item.i_astrological_sign, folder='i_astrological_sign', extension='png'),
            'stamps': staticImageURL('stamp.png'),
        }, extra_fields=extra_fields, exclude_fields=exclude_fields, **kwargs)

        if 'square_image' in fields:
            del(fields['square_image'])

        if 'band' in fields:
            fields['band'] = bandField(item.band, item.i_band)

        if item.classroom is not None and item.school is not None:
            setSubField(fields, 'school', key='type', value='text_annotation')
            setSubField(fields, 'school', key='annotation', value= item.classroom)
        setSubField(fields, 'birthday', key='type', value='text')
        setSubField(fields, 'birthday', key='value', value=lambda f: date_format(item.birthday, format='MONTH_DAY_FORMAT', use_l10n=True))
        setSubField(fields, 'height', key='value', value=u'{} cm'.format(item.height))
        setSubField(fields, 'description', key='type', value='long_text')

        setSubField(fields, 'alt_name', key='verbose_name', value=_('Name'))
        if item.alt_name is not None:
            setSubField(fields, 'name', key='icon', value='rock')
            setSubField(fields, 'name', key='verbose_name', value=string_concat(_('Name'), ' (', _('Stage'), ')'))
            
        if item.romaji_CV == item.CV or get_language() == 'ja':
            setSubField(fields, 'CV', key='verbose_name', value=_('CV'))
            if 'romaji_CV' in fields:
                del(fields['romaji_CV'])
                
        return fields

    filter_cuteform = {
        'i_band': {
            'image_folder': 'band',
            'to_cuteform': 'value',
            'title': _('Band'),
            'extra_settings': {
                'modal': 'true',
                'modal-text': 'true',
            },
        },
        'i_school_year': {
            'type': CuteFormType.HTML,
        },
        'i_astrological_sign': {},
    }

    class ListView(MainItemCollection.ListView):
        item_template = custom_item_template
        filter_form = forms.MemberFilterForm
        per_line = 5
        page_size = 35

        def get_page_title(self):
            return _('{things} list').format(things=_('Characters'))

    class ItemView(MainItemCollection.ItemView):
        def get_queryset(self, queryset, parameters, request):
            queryset = super(MemberCollection.ItemView, self).get_queryset(queryset, parameters, request)
            queryset = queryset.prefetch_related(
                Prefetch('cards', queryset=models.Card.objects.order_by('-release_date')),
                Prefetch('associated_costume', queryset=models.Costume.objects.order_by(
                    '-id').select_related('card', 'member')),
            )
            return queryset

        def to_fields(self, item, prefetched_together=None, *args, **kwargs):
            if prefetched_together is None: prefetched_together = []
            prefetched_together += [
                'cards', 'associated_costume',
                'officialarts', 'comics', 'stamps',
                'fans',
            ]
            fields = super(MemberCollection.ItemView, self).to_fields(
                item, prefetched_together=prefetched_together, *args, **kwargs)

            # Use presets URLs for SEO
            for field_name, preset in [
                    (u'cards', item.name),
                    (u'associated_costume', item.name),
                    (u'officialarts', u'officialart-{}'.format(item.name)),
                    (u'comics', u'comic-{}'.format(item.name)),
                    (u'stamps', u'stamp-{}'.format(item.name)),
            ]:
                if field_name in fields:
                    and_more = fields[field_name].get('and_more')
                    if and_more:
                        and_more['link'] = u'/{}/{}/'.format(
                            and_more['link'].split('/')[1],
                            tourldash(preset),
                        )
                        and_more['ajax_link'] = u'/ajax/{}/{}/?ajax_modal_only'.format(
                            and_more['ajax_link'].split('/')[2],
                            tourldash(preset),
                        )

            return fields

############################################################
# Favorite Card Collection

def to_FavoriteCardCollection(cls):
    class _FavoriteCardCollection(cls):
        @property
        def title(self):
            return _('Favorite {thing}').format(thing=_('Card').lower())

        @property
        def plural_title(self):
            return _('Favorite {things}').format(things=_('Cards').lower())

        filter_cuteform = CardCollection.ListView.filter_cuteform.copy()

        class ListView(cls.ListView):
            item_template = 'cardItem'
            per_line = 2
            ajax_pagination_callback = 'loadCardInList'
            show_item_buttons = True
            filter_form = forms.to_CollectibleCardFilterForm(cls)

        class AddView(cls.AddView):
            unique_per_owner = True
            quick_add_to_collection = justReturn(True)

        class EditView(cls.EditView):
            def extra_context(self, context):
                edit_form = context.get('forms', {}).get('edit_favoritecard', None)
                if edit_form is not None:
                    edit_form.beforeform = mark_safe(u'<div class="hidden">')
                    edit_form.belowform = mark_safe(u'</div>')

    return _FavoriteCardCollection

############################################################
# Collectible Card Collection

def to_CollectibleCardCollection(cls):
    class _CollectibleCardCollection(cls):
        title = _('Card')
        plural_title = _('Cards')
        form_class = forms.to_CollectibleCardForm(cls)

        filter_cuteform = CardCollection.ListView.filter_cuteform.copy()
        _f = filter_cuteform.update({
            'max_leveled': {
                'type': CuteFormType.YesNo,
            },
            'first_episode': {
                'type': CuteFormType.YesNo,
            },
            'memorial_episode': {
                'type': CuteFormType.YesNo,
            },
        })

        fields_icons = {
            'trained': 'idolized',
            'max_leveled': 'max-level',
            'first_episode': 'play',
            'memorial_episode': 'play',
            'skill_level': 'skill',
            'card': 'deck',
        }

        fields_order = [
            'card', 'trained', 'max_leveled',
            'performance', 'technique', 'visual', 'overall',
            'first_episode', 'memorial_episode', 'skill_level',
        ]


        def to_fields(self, view, item, exclude_fields=None, extra_fields=None, *args, **kwargs):
            if exclude_fields is None: exclude_fields = []
            if extra_fields is None: extra_fields = []
            exclude_fields.append('prefer_untrained')
            if item.card.i_rarity not in models.Card.TRAINABLE_RARITIES:
                exclude_fields.append('trained')
            # Add stats
            stats = dict(item.card.stats_percent)
            stats = stats['trained_max'] if item.trained else stats['max']
            extra_fields += [
                (stat, {
                    'verbose_name': verbose_name,
                    'verbose_name_subtitle': _(u'Level {level}').format(
                        level=item.card.max_level_trained if item.trained else item.card.max_level,
                    ).replace(' ', u'\u00A0'),
                    'value': value,
                    'type': 'text',
                    'icon': 'skill' if stat != 'overall' else 'center',
                })
                for stat, verbose_name, value, _max, _percentage in stats
            ]
            # Add skill
            if item.card.skill_type:
                extra_fields.append(('skill', {
                    'title': mark_safe(u'{} <span class="text-muted">({})</span>'.format(
                        item.card.t_skill_type.replace(' ', u'\u00A0'),
                        item.card.t_side_skill_type.replace(' ', u'\u00A0')))
                    if item.card.i_side_skill_type else item.card.t_skill_type,
                    'verbose_name': _('Skill'),
                    'icon': item.card.skill_icon,
                    'value': item.full_skill,
                    'type': 'title_text',
                }))

            fields = super(_CollectibleCardCollection, self).to_fields(
                view, item, *args, exclude_fields=exclude_fields, extra_fields=extra_fields, **kwargs)
            setSubField(fields, 'card', key='value', value=u'#{}'.format(item.card.id))
            setSubField(fields, 'first_episode', key='verbose_name', value=_('{nth} episode').format(nth=_('1st')))
            return fields

        class ListView(cls.ListView):
            col_break = 'xs'
            filter_form = forms.to_CollectibleCardFilterForm(cls)

            def get_queryset(self, queryset, parameters, request):
                queryset = super(_CollectibleCardCollection.ListView, self).get_queryset(queryset, parameters, request)
                if request.GET.get('ordering', None) in ['card___overall_max', 'card___overall_trained_max']:
                    queryset = queryset.extra(select={
                        'card___overall_max': 'performance_max + technique_max + visual_max',
                        'card___overall_trained_max': 'performance_trained_max + technique_trained_max + visual_trained_max',
                    })
                return queryset

        class AddView(cls.AddView):
            unique_per_owner = True
            ajax_callback = 'loadCollecticleCardForm'

            def quick_add_to_collection(self, request):
                return request.GET.get('view') == 'icons'

            add_to_collection_variables = cls.AddView.add_to_collection_variables + [
                'i_rarity',
            ]

        class EditView(cls.EditView):
            ajax_callback = 'loadCollecticleCardForm'

    return _CollectibleCardCollection

############################################################
# Card Collection

CARD_CUTEFORM = {
    'i_rarity': {
        'type': CuteFormType.HTML,
        'to_cuteform': lambda k, v: rarity_to_stars_images(k),
    },
    'i_attribute': {},
    'trainable': {
        'type': CuteFormType.OnlyNone,
    },
    'i_skill_type': {
        'to_cuteform': lambda k, v: CardCollection._skill_icons[k],
        'transform': CuteFormTransform.Flaticon,
    },
    'member_band': {
        'to_cuteform': lambda k, v: (
            getCharacterImageFromPk(int(k[7:]))
            if k.startswith('member-')
            else staticImageURL(v, folder='band', extension='png')
        ),
        'title': string_concat(_('Member'), ' / ', _('Band')),
        'extra_settings': {
            'modal': 'true',
            'modal-text': 'true',
        },
    },
    'version': {
        'to_cuteform': lambda k, v: CardCollection._version_images[k],
        'image_folder': 'language',
        'transform': CuteFormTransform.ImagePath,
    },
    'origin': {
        'transform': CuteFormTransform.Flaticon,
        'to_cuteform': lambda k, v: CardCollection._origin_to_cuteform[k],
    },
    'gacha_type': {
        'transform': CuteFormTransform.Flaticon,
        'to_cuteform': lambda k, v: GachaCollection._gacha_type_to_cuteform[k],
    },
}

CARD_CUTEFORM_EDIT = CARD_CUTEFORM.copy()
CARD_CUTEFORM_EDIT['member'] = {
    'to_cuteform': lambda k, v: getCharacterImageFromPk(k),
    'title': _('Member'),
    'extra_settings': {
        'modal': 'true',
        'modal-text': 'true',
    },
}

CARDS_STATS_FIELDS = [
    u'{}{}'.format(_st, _sf) for _st in [
        'performance', 'technique', 'visual', 'overall',
    ] for _sf in [
        '_min', '_max', '_trained_max',
    ]
]

CARDS_ICONS = { _st: 'skill' for _st in CARDS_STATS_FIELDS }
CARDS_ICONS.update({
    'rarity': 'star',
    'member': 'idol',
    'name': 'id',
    'versions': 'world',
    'is_promo': 'promo',
    'is_original': 'deck',
    'release_date': 'date',
    'favorited': 'heart',
    'collectedcards': 'deck',
})

CARDS_ORDER = [
    'id', 'card_name', 'member', 'cameo_members', 'rarity', 'attribute', 'versions', 'is_promo', 'is_original',
    'release_date',
    'skill_name', 'skill_type', 'japanese_skill',
    'gacha', 'arts', 'transparents', 'chibis', 'associated_costume', 'images',
]

CARDS_STATISTICS_ORDER = [
    'image', 'image_trained',
] + CARDS_STATS_FIELDS + [
    'skill_type',
]

CARDS_EXCLUDE = [
    'name', 'i_side_skill_type', 'skill_name',
    'image_trained', 'art', 'art_trained', 'transparent', 'transparent_trained',
] + CARDS_STATS_FIELDS + [
    'i_skill_note_type', 'skill_stamina', 'skill_alt_stamina', 'skill_duration',
    'skill_percentage', 'skill_alt_percentage', 'i_skill_special', 'i_skill_influence', 'skill_cond_percentage',
]

class CardCollection(MainItemCollection):
    queryset = models.Card.objects.all()
    title = _('Card')
    plural_title = _('Cards')
    icon = 'deck'
    navbar_link_list = 'girlsbandparty'

    form_class = forms.CardForm
    translated_fields = ('name', 'skill_name', )
    show_collect_total = {
        'collectiblecard': False,
    }

    _skill_icons = { _i: _c['icon'] for _i, _c in models.Card.SKILL_TYPES.items() }
    _version_images = { _vn: _v['image'] for _vn, _v in models.Account.VERSIONS.items() }
    _origin_to_cuteform = {
        'is_original': 'deck',
        'is_promo': 'promo',
        'is_gacha': 'scout-box',
        'is_event': 'event',
    }
    collectible = [
        models.CollectibleCard,
        models.FavoriteCard,
    ]

    def collectible_to_class(self, model_class):
        cls = super(CardCollection, self).collectible_to_class(model_class)
        if model_class.collection_name == 'favoritecard':
            return to_FavoriteCardCollection(cls)
        return to_CollectibleCardCollection(cls)

    def to_fields(self, view, item, *args, **kwargs):
        fields = super(CardCollection, self).to_fields(view, item, *args, icons=CARDS_ICONS, images={
            'attribute': u'{static_url}img/i_attribute/{value}.png'.format(
                static_url=RAW_CONTEXT['static_url'],
                value=item.i_attribute,
            ),
        }, **kwargs)
        setSubField(fields, 'rarity', key='type', value='html')
        setSubField(fields, 'rarity', key='value', value=lambda f: rarity_to_stars_images(item.i_rarity))
        return fields

    def buttons_per_item(self, view, request, context, item):
        buttons = super(CardCollection, self).buttons_per_item(view, request, context, item)
        if 'favoritecard' in buttons:
            if view.view == 'list_view':
                buttons['favoritecard']['icon'] = 'star'

        if request.user.is_authenticated() and request.user.hasPermission('manage_main_items'):
            for field in ['art', 'art_trained'] if item.trainable else ['transparent', 'transparent_trained']:
                if getattr(item, field):
                    buttons[u'preview_{}'.format(field)] = {
                        'classes': self.item_buttons_classes + ['staff-only'],
                        'show': True,
                        'url': (
                            u'/?foreground_preview={}'.format(
                                getattr(item, u'{}_url'.format(field)))
                            if not item.trainable or (not item.art and not item.art_trained)
                            else u'/?preview={}'.format(
                                    getattr(item, u'{}_2x_url'.format(field))
                                    or getattr(item, u'{}_original_url'.format(field)))
                        ),
                        'icon': 'link',
                        'title': u'Preview {} on homepage'.format(field.replace('_', ' ')),
                        'has_permissions': True,
                        'open_in_new_window': True,
                    }
        return buttons

    class ItemView(MainItemCollection.ItemView):
        top_illustration = 'items/cardItem'
        ajax_callback = 'loadCard'

        def get_queryset(self, queryset, parameters, request):
            queryset = super(CardCollection.ItemView, self).get_queryset(queryset, parameters, request)
            return queryset.select_related('associated_costume')

        def to_fields(self, item, extra_fields=None, exclude_fields=None,
                      order=None, *args, **kwargs):
            if extra_fields is None: extra_fields = []
            if exclude_fields is None: exclude_fields = []
            language = get_language()

            # Add id field
            extra_fields.append(('id', {
                'verbose_name': _(u'ID'),
                'type': 'text',
                'value': item.id,
                'icon': 'id',
            }))

            # Add Title
            title = item.names.get(language, item.name if language not in settings.LANGUAGES_CANT_SPEAK_ENGLISH else None)
            value = item.japanese_name or item.name
            if value is not None:
                extra_fields.append(('card_name', {
                    'verbose_name': _('Title'),
                    'icon': 'id',
                    'type': 'title_text' if title not in [value, None] else 'text',
                    'title': title,
                    'value': value,
                }))

            # Add Skill Name
            title = item.skill_names.get(language, item.skill_name if language not in settings.LANGUAGES_CANT_SPEAK_ENGLISH else None)
            value = item.japanese_skill_name or item.skill_name
            if value is not None:
                extra_fields.append(('skill_name', {
                    'verbose_name': _('Skill name'),
                    'icon': 'skill',
                    'type': 'title_text' if title not in [value, None] else 'text',
                    'title': title,
                    'value': value,
                }))

            # Add skill details
            if item.i_skill_type:
                extra_fields.append(('japanese_skill', {
                    'verbose_name': _('Skill'),
                    'verbose_name_subtitle': t['Japanese'] if language != 'ja' else None,
                    'icon': item.skill_icon,
                    'type': 'title_text',
                    'title': mark_safe(u'{} <span class="text-muted">({})</span>'.format(item.japanese_skill_type, item.japanese_side_skill_type)
                                       if item.i_side_skill_type else item.japanese_skill_type),
                    'value': item.japanese_full_skill,
                }))
            # Add gacha and events
            for cached_event in (item.cached_events or []):
                extra_fields.append((u'event-{}'.format(cached_event.id), subtitledImageLink(cached_event, _('Event'), icon='event', subtitle=cached_event.unicode)))
            for cached_gacha in (item.cached_gachas or []):
                extra_fields.append((u'gacha-{}'.format(cached_gacha.id), subtitledImageLink(cached_gacha, _('Gacha'), image=staticImageURL('gacha.png'), subtitle=cached_gacha.unicode)))
            # Add images fields
            for image, verbose_name in [('image', _('Icon')), ('art', _('Art')), ('transparent', _('Transparent'))]:
                if getattr(item, image):
                    extra_fields.append((u'{}s'.format(image), {
                        'verbose_name': verbose_name,
                        'type': 'images_links',
                        'images': [{
                            'value': thumbnail_url,
                            'link': image_url,
                            'verbose_name': verbose_name,
                            'link_text': verbose_name,
                        } for image_url, thumbnail_url in [
                            (getattr(item, u'{}_original_url'.format(image)),
                             getattr(item, u'{}_thumbnail_url'.format(image))),
                            (getattr(item, u'{}_trained_original_url'.format(image)),
                             getattr(item, u'{}_trained_thumbnail_url'.format(image))),
                        ] if image_url],
                        'icon': 'pictures',
                    }))
            # Add cameos
            if item.cached_cameos:
                extra_fields.append(('cameo_members', {
                    'icon': 'users',
                    'verbose_name': _('Cameos'),
                    'type': 'images_links',
                    'images': [{
                        'value': cameo.image_url,
                        'link': cameo.item_url,
                        'ajax_link': cameo.ajax_item_url,
                        'link_text': cameo.name,
                    } for cameo in item.cached_cameos]
                }))
            # Add live2d viewer and chibis
            if hasattr(item, 'associated_costume'):
                item.associated_costume.chibis = item.associated_costume.owned_chibis.all()
                if item.associated_costume.chibis:
                    extra_fields.append(('chibis', {
                        'icon': 'pictures',
                        'type': 'images_links',
                        'verbose_name': _('Chibi'),
                        'images': [{
                            'value': chibi.image_url,
                            'link': chibi.image_original_url,
                            'link_text': u'{} - {}'.format(unicode(item), _('Chibi')),
                            'verbose_name': _('Chibi'),
                        } for chibi in item.associated_costume.chibis],
                    }))

                to_cos_link = lambda text, classes=None: u'<a href="{url}" target="_blank" class="{classes}" data-ajax-url="{ajax_url}" data-ajax-title="{ajax_title}">{text}</a>'.format(
                    url=item.associated_costume.item_url,
                    ajax_url=item.associated_costume.ajax_item_url + "?from_card",
                    ajax_title=string_concat(_("Costume"), " - ", unicode(item)),
                    text=text,
                    classes=classes or '',
                )
                extra_fields.append(('associated_costume', {
                    'icon': 'dress',
                    'verbose_name': _('Costume'),
                    'type': 'html',
                    'value': mark_safe(u'{} {}'.format(
                        to_cos_link(_('View model'), classes='btn btn-lg btn-secondary'),
                        to_cos_link(u'<img src="{url}" alt="{item} preview">'.format(
                            url=item.associated_costume.image_thumbnail_url,
                            item=unicode(item),
                        )) if item.associated_costume.image_url else '',
                    ))
                }))

            # Exclude fields
            if exclude_fields == 1:
                exclude_fields = []
            else:
                exclude_fields += CARDS_EXCLUDE + (['versions', 'i_skill_type'] if language == 'ja' else [])
            exclude_fields += ['show_art_on_homepage', 'show_trained_art_on_homepage']
            # Order
            if order is None:
                order = CARDS_ORDER

            fields = super(CardCollection.ItemView, self).to_fields(
                item, *args, extra_fields=extra_fields, exclude_fields=exclude_fields,
                order=order, **kwargs)
            # Modify existing fields
            # skill deTails
            setSubField(fields, 'skill_type', key='type', value='title_text')
            setSubField(fields, 'skill_type', key='title',
                        value=lambda k: mark_safe(u'{} <span class="text-muted">({})</span>'.format(item.t_skill_type, item.t_side_skill_type)
                        if item.i_side_skill_type else item.t_skill_type))
            setSubField(fields, 'skill_type', key='value', value=item.full_skill)
            setSubField(fields, 'skill_type', key='icon', value=lambda k: item.skill_icon)
            # Totals
            setSubField(fields, 'favorited', key='link', value=u'/users/?favorited_card={}'.format(item.id))
            setSubField(fields, 'favorited', key='ajax_link', value=u'/ajax/users/?favorited_card={}&ajax_modal_only'.format(item.id))
            setSubField(fields, 'collectedcards', key='link', value=u'/accounts/?collected_card={}'.format(item.id))
            setSubField(fields, 'collectedcards', key='ajax_link', value=u'/ajax/accounts/?collected_card={}&ajax_modal_only'.format(item.id))
            # If there's only one art + one transparent, merge fields:
            if item.art and not item.art_trained and item.transparent and not item.transparent_trained:
                setSubField(fields, 'arts', key='verbose_name', value=u'{} / {}'.format(_('Art'), _('Transparent')))
                setSubField(fields, 'arts', key='images', value=[{
                    'value': thumbnail_url,
                    'link': image_url,
                    'verbose_name': verbose_name,
                    'link_text': verbose_name,
                } for image_url, thumbnail_url, verbose_name in [
                    (getattr(item, u'art_original_url'), getattr(item, u'art_thumbnail_url'), _('Art')),
                    (getattr(item, u'transparent_original_url'), getattr(item, u'transparent_thumbnail_url'), _('Transparent')),
                ]])
                if 'transparents' in fields:
                    del(fields['transparents'])
            # hide is promo, is original
            if not item.is_promo and 'is_promo' in fields:
                del(fields['is_promo'])
            if not item.is_original and 'is_original' in fields:
                del(fields['is_original'])
            return fields

    class ListView(MainItemCollection.ListView):
        item_template = custom_item_template
        per_line = 2
        page_size = 12
        filter_form = forms.CardFilterForm
        ajax_pagination_callback = 'loadCardInList'
        filter_cuteform = CARD_CUTEFORM

        quick_add_view = 'icons'

        alt_views = MainItemCollection.ListView.alt_views + [
            ('icons', { 'verbose_name': string_concat(_('Icons'), ' (', _('Quick add'), ')') }),
            ('statistics', {
                'verbose_name': _('Statistics'),
                'template': 'default_item_table_view',
                'display_style': 'table',
                'display_style_table_fields': [
                    'image', 'image_trained',
                    'performance_min', 'performance_max', 'performance_trained_max',
                    'technique_min', 'technique_max', 'technique_trained_max',
                    'visual_min', 'visual_max', 'visual_trained_max',
                    'overall_min', 'overall_max', 'overall_trained_max',
                    'skill_type',
                ],
            }),
        ]

        def get_queryset(self, queryset, parameters, request):
            queryset = super(CardCollection.ListView, self).get_queryset(queryset, parameters, request)
            if request.GET.get('ordering', None) in ['_overall_max', '_overall_trained_max']:
                queryset = queryset.extra(select={
                    '_overall_max': 'performance_max + technique_max + visual_max',
                    '_overall_trained_max': 'performance_trained_max + technique_trained_max + visual_trained_max',
                })
            return queryset

        def extra_context(self, context):
            context['view'] = context['request'].GET.get('view', None)
            if context['view'] == 'icons':
                context['per_line'] = 6
                context['col_size'] = int(math.ceil(12 / context['per_line']))
                context['col_break'] = 'xs'
                for item in context['items']:
                    item.show_item_buttons_as_icons = True
            if context['view'] == 'statistics':
                context['full_width'] = True
                context['include_below_item'] = False
            return context

        def ordering_fields(self, item, only_fields=None, exclude_fields=None, *args, **kwargs):
            if exclude_fields is None: exclude_fields = []
            exclude_fields += ['i_rarity']
            fields = super(CardCollection.ListView, self).ordering_fields(item, *args, only_fields=only_fields, exclude_fields=exclude_fields, **kwargs)
            if '_overall_max' in only_fields:
                fields['overall_max'] = {
                    'verbose_name': string_concat(_('Overall'), ' (', _('Maximum'), ')'),
                    'value': item._overall_max,
                    'type': 'text',
                    'icon': 'skill',
                }
            if '_overall_trained_max' in only_fields:
                fields['overall_trained_max'] = {
                    'verbose_name': string_concat(_('Overall'), ' (', _('Trained'), ', ', _('Maximum'), ')'),
                    'value': item._overall_trained_max,
                    'type': 'text',
                    'icon': 'skill',
                }
            return fields

        def table_fields(self, item, order=None, extra_fields=None, exclude_fields=None, *args, **kwargs):
            if extra_fields is None: extra_fields = []
            if exclude_fields is None: exclude_fields = []
            if order is None:
                order = CARDS_STATISTICS_ORDER
            extra_fields += [
                (u'overall_{}'.format(suffix), { 'value': getattr(item, u'overall_{}'.format(suffix)) })
                for suffix in ['min', 'max', 'trained_max']
            ]
            fields = super(CardCollection.ListView, self).table_fields(
                item, *args, exclude_fields=1, extra_fields=extra_fields, order=order, **kwargs)
            for field_name in ['image', 'image_trained']:
                if item.trainable or 'trained' not in field_name:
                    setSubField(fields, field_name, key='type', value='image_link')
                    setSubField(fields, field_name, key='link', value=item.item_url)
                    setSubField(fields, field_name, key='ajax_link', value=item.ajax_item_url)
                    setSubField(fields, field_name, key='link_text', value=unicode(item))
            # Hide trained fields for cards that are not trainable
            if not item.trainable:
                for field_name in ['image_trained', 'performance_trained_max', 'technique_trained_max', 'visual_trained_max', 'overall_trained_max']:
                    setSubField(fields, field_name, key='type', value='text')
                    setSubField(fields, field_name, key='value', value='')
            return fields

        def table_fields_headers_sections(self, view):
            return [
                ('', '', 2),
                ('performance', _('Performance'), 3),
                ('technique', _('Technique'), 3),
                ('visual', _('Visual'), 3),
                ('overall', _('Overall'), 3),
                ('skill', _('Skill'), 1),
            ]

        def table_fields_headers(self, fields, view=None):
            return [('image', ''), ('image_trained', '')] + [
                (u'{}_{}'.format(name, suffix), verbose_name)
                for name in ['performance', 'technique', 'visual', 'overall']
                for suffix, verbose_name in [
                        ('min', _('Min')), ('max', _('Max')),
                        ('trained_max', _('Trained')),
                ]] + [('skill_type', '')]

    def _extra_context_for_form(self, context):
        if 'js_variables' not in context:
            context['js_variables'] = {}
        context['js_variables']['all_variables'] = models.Card.ALL_VARIABLES
        context['js_variables']['variables_per_skill_type'] = models.Card.VARIABLES_PER_SKILL_TYPES
        context['js_variables']['special_cases_variables'] = models.Card.SPECIAL_CASES_VARIABLES
        context['js_variables']['template_per_skill_type'] = models.Card.TEMPLATE_PER_SKILL_TYPES
        context['js_variables']['special_cases_template'] = models.Card.SPECIAL_CASES_TEMPLATE

    class AddView(MainItemCollection.AddView):
        ajax_callback = 'loadCardForm'

        def extra_context(self, context):
            super(CardCollection.AddView, self).extra_context(context)
            self.collection._extra_context_for_form(context)

    class EditView(MainItemCollection.EditView):
        ajax_callback = 'loadCardForm'
        filter_cuteform = CARD_CUTEFORM_EDIT

        def extra_context(self, context):
            super(CardCollection.EditView, self).extra_context(context)
            self.collection._extra_context_for_form(context)

############################################################
# Event Participation Collection

def to_EventParticipationCollection(cls):
    class _EventParticipationCollection(cls):
        title = _('Participated event')
        plural_title = _('Participated events')
        collectible_tab_name = _('Events')
        show_edit_button_superuser_only = True
        form_class = forms.to_EventParticipationForm(cls)
        reportable = True
        report_allow_delete = False

        report_edit_templates = OrderedDict([
            ('Unrealistic Score', 'Your score is unrealistic, so we edited it. If this was a mistake, please upload a screenshot of your game to the details of your event participation to prove your score and change it back. Thank you for your understanding.'),
            ('Unrealistic Ranking', 'Your ranking is unrealistic, so we edited it. If this was a mistake, please upload a screenshot of your game to the details of your event participation to prove your score and change it back. Thank you for your understanding.'),
            ('Unrealistic Song Score', 'Your song score is unrealistic, so we edited it. If this was a mistake, please upload a screenshot of your game to the details of your event participation to prove your score and change it back. Thank you for your understanding.'),
            ('Unrealistic Song Ranking', 'Your song ranking is unrealistic, so we edited it. If this was a mistake, please upload a screenshot of your game to the details of your event participation to prove your score and change it back. Thank you for your understanding.'),
        ])

        filter_cuteform = {
            'i_version': {
                'to_cuteform': lambda k, v: AccountCollection._version_images[k],
                'image_folder': 'language',
                'transform': CuteFormTransform.ImagePath,
            },
            'is_goal_master': { 'type': CuteFormType.YesNo, },
            'is_ex_goal_master': { 'type': CuteFormType.YesNo, },
        }

        fields_icons = {
            'score': 'scoreup',
            'ranking': 'trophy',
            'song_score': 'song',
            'song_ranking': 'trophy',
            'is_goal_master': 'achievement',
            'is_ex_goal_master': 'achievement',
            'screenshot': 'screenshot',
            'event': 'event',
        }

        class AddView(cls.AddView):
            unique_per_owner = True
            add_to_collection_variables = cls.AddView.add_to_collection_variables + [
                'i_type',
            ]

        class ListView(cls.ListView):
            per_line = 3
            filter_form = forms.to_EventParticipationFilterForm(cls)
            show_item_buttons_as_icons = True
            show_item_buttons_justified = False

            alt_views = cls.ListView.alt_views + [
                ('leaderboard', {
                    'verbose_name': _('Leaderboard'),
                    'template': 'eventParticipationLeaderboard',
                    'per_line': 1,
                    'full_width': True,
                    'hide_in_filter': True,
                    'hide_in_navbar': True,
                }),
            ]

            def get_queryset(self, queryset, parameters, request):
                queryset = super(_EventParticipationCollection.ListView, self).get_queryset(queryset, parameters, request)
                if request.GET.get('view', None) == 'leaderboard':
                    queryset = queryset.select_related('account')
                    if request.GET.get('i_version', None) is not None:
                        queryset = queryset.exclude(ranking__isnull=True).exclude(ranking=0)
                return queryset

            def extra_context(self, context):
                super(_EventParticipationCollection.ListView, self).extra_context(context)
                if context['view'] == 'leaderboard':
                    context['show_relevant_fields_on_ordering'] = False

    return _EventParticipationCollection

############################################################
# Event Collection

EVENT_ITEM_FIELDS_ORDER_BEFORE = [
    'name', 'type',
]

EVENT_ITEM_FIELDS_ORDER_AFTER = [
    'participations', 'boost_attribute', 'boost_stat', 'boost_members', 'cards',
]

EVENT_ICONS = {
    'name': 'event',
    'participations': 'contest',
    'start_date': 'date', 'end_date': 'date',
    'english_start_date': 'date', 'english_end_date': 'date',
    'taiwanese_start_date': 'date', 'taiwanese_end_date': 'date',
    'korean_start_date': 'date', 'korean_end_date': 'date',
    'type': 'category', 'boost_stat': 'statistics',
}

EVENT_CUTEFORM = {
    'main_card': {
        'to_cuteform': lambda k, v: v.image_url,
        'title': _('Card'),
        'extra_settings': {
            'modal': 'true',
            'modal-text': 'true',
        },
    },
    'secondary_card': {
        'to_cuteform': lambda k, v: v.image_url,
        'title': _('Card'),
        'extra_settings': {
            'modal': 'true',
            'modal-text': 'true',
        },
    },
    'i_boost_attribute': {
        'image_folder': 'i_attribute',
    },
     'i_boost_stat': {
        'type': CuteFormType.HTML,
        'to_cuteform': lambda k, v: format_html(
            u'<span data-toggle="tooltip" title="{}">{}</div>', unicode(v), v[0]),
    },
    'version': {
        'to_cuteform': lambda k, v: CardCollection._version_images[k],
        'image_folder': 'language',
        'transform': CuteFormTransform.ImagePath,
    },
}

EVENT_LIST_ITEM_CUTEFORM = EVENT_CUTEFORM.copy()
EVENT_LIST_ITEM_CUTEFORM['boost_members'] = {
    'to_cuteform': lambda k, v: getCharacterImageFromPk(k),
    'title': _('Boost members'),
    'extra_settings': {
        'modal': 'true',
        'modal-text': 'true',
    },
}

EVENT_LIST_ITEM_CUTEFORM['status'] = {
    'type': CuteFormType.HTML,
}

class EventCollection(MainItemCollection):
    queryset = models.Event.objects.all()
    title = _('Event')
    plural_title = _('Events')
    icon = 'event'
    form_class = forms.EventForm
    translated_fields = ('name', )
    navbar_link_list = 'girlsbandparty'

    filter_cuteform = EVENT_LIST_ITEM_CUTEFORM

    collectible = models.EventParticipation

    share_image = justReturn('screenshots/events.png')
    auto_share_image = False

    def collectible_to_class(self, model_class):
        cls = super(EventCollection, self).collectible_to_class(model_class)
        if model_class.collection_name == 'eventparticipation':
            return to_EventParticipationCollection(cls)
        return cls

    def to_fields(self, view, item, *args, **kwargs):
        fields = super(EventCollection, self).to_fields(view, item, *args, icons=EVENT_ICONS, images={
            'boost_attribute': staticImageURL(item.i_boost_attribute, folder='i_attribute', extension='png'),
            'english_image': staticImageURL('language/world.png'),
            'taiwanese_image': staticImageURL('language/zh-hant.png'),
            'korean_image': staticImageURL('language/kr.png'),
        }, **kwargs)
        if get_language() == 'ja' and 'name' in fields and 'japanese_name' in fields:
            setSubField(fields, 'japanese_name', key='verbose_name', value=fields['name']['verbose_name'])
            del(fields['name'])
        if item.name == item.japanese_name and 'japanese_name' in fields:
            del(fields['japanese_name'])

        for version, version_details in models.Event.VERSIONS.items():
            setSubField(
                fields, u'{}start_date'.format(version_details['prefix']),
                key='timezones', value=[version_details['timezone'], 'Local time'],
            )
            setSubField(
                fields, u'{}end_date'.format(version_details['prefix']),
                key='timezones', value=[version_details['timezone'], 'Local time'],
            )

        if get_language() in models.ALT_LANGUAGES_EXCEPT_JP_KEYS and unicode(item.name) != unicode(item.t_name):
            setSubField(fields, 'name', key='value', value=mark_safe(u'{}<br><span class="text-muted">{}</span>'.format(item.name, item.t_name)))

        return fields

    class ListView(MainItemCollection.ListView):
        per_line = 2
        ajax_callback = 'loadEventInList'
        filter_form = forms.EventFilterForm
        show_collect_button = {
            'eventparticipation': False,
        }

    class ItemView(MainItemCollection.ItemView):
        template = 'default'
        ajax_callback = 'loadEventGacha'

        def get_queryset(self, queryset, parameters, request):
            queryset = super(EventCollection.ItemView, self).get_queryset(queryset, parameters, request)
            queryset = queryset.select_related('main_card', 'secondary_card').prefetch_related(
                Prefetch('boost_members', to_attr='all_members'),
                Prefetch('gachas', to_attr='all_gachas'),
                Prefetch('gift_songs', to_attr='all_gifted_songs'),
                Prefetch('reruns', to_attr='all_reruns'),
                Prefetch('assets', queryset=models.Asset.objects.select_related(
                    'song').order_by('i_type'), to_attr='all_assets'),
            )
            return queryset

        def extra_context(self, context):
            if 'js_variables' not in context:
                context['js_variables'] = {}
            context['js_variables']['versions_prefixes'] = models.Account.VERSIONS_PREFIXES

            if hasattr(context['request'], 'fields_per_version'):
                context['js_variables']['fields_per_version'] = (
                    models.Event.FIELDS_PER_VERSION
                    + context['request'].fields_per_version
                )
            else:
                context['js_variables']['fields_per_version'] = models.Event.FIELDS_PER_VERSION

        def to_fields(self, item, order=None, extra_fields=None, exclude_fields=None, request=None, *args, **kwargs):
            if extra_fields is None: extra_fields = []
            if exclude_fields is None: exclude_fields = []
            if order is None: order = []

            new_order = EVENT_ITEM_FIELDS_ORDER_BEFORE[:]

            orders_per_versions = OrderedDict([
                (version_name, [
                    u'{}{}'.format(version['prefix'], _f)
                    for _f in models.Event.FIELDS_PER_VERSION
                ])
                for version_name, version in models.Account.VERSIONS.items()
            ])
            fields_per_version = {}

            for version in models.Account.VERSIONS.values():
                start_date = getattr(item, u'{}start_date'.format(version['prefix']))
                end_date = getattr(item, u'{}end_date'.format(version['prefix']))
                image = getattr(item, u'{}image'.format(version['prefix']))

                ## Create Countdowns for Events that are active
                status = getattr(item, u'{}status'.format(version['prefix']))
                if status and status not in ['ended', 'invalid']:
                    extra_fields += [
                        (u'{}countdown'.format(version['prefix']), {
                            'verbose_name': _('Countdown'),
                            'value': mark_safe(toCountDown(
                                date=end_date if status == 'current' else start_date,
                                sentence=_('{time} left') if status == 'current' else _('Starts in {time}'),
                                classes=['fontx1-5'],
                            )),
                            'icon': 'times',
                            'type': 'html',
                        }),
                    ]
                ## Create image fields with placeholders when needed
                if not image and (start_date or end_date):
                    extra_fields.append(('{}image'.format(version['prefix']), {
                        'image': staticImageURL(version['image'], folder='language', extension='png'),
                        'type': 'html',
                        'value': u'<hr>',
                    }))

            # Add Image
            if item.image:
                extra_fields.append(('image', {
                    'image': staticImageURL('language/ja.png'),
                    'type': 'image',
                    'value': item.image_url,
                }))
            if len(item.all_gachas):
                for gacha in item.all_gachas:
                    extra_fields.append((u'gacha-{}'.format(gacha.id),  subtitledImageLink(gacha, _('Gacha'), image=staticImageURL('gacha.png'))))
            if len(item.all_members):
                extra_fields.append(('boost_members', {
                    'icon': 'users',
                    'verbose_name': _('Boost Members'),
                    'type': 'images_links',
                    'images': [{
                        'value': member.square_image_url,
                        'link': member.item_url,
                        'ajax_link': member.ajax_item_url,
                        'link_text': unicode(member),
                    } for member in item.all_members]
                }))
            if item.main_card_id or item.secondary_card_id:
                extra_fields.append(('cards', {
                    'icon': 'cards',
                    'verbose_name': _('Cards'),
                    'type': 'images_links',
                    'images': [{
                        'value': card.image_url,
                        'link': card.item_url,
                        'ajax_link': card.ajax_item_url,
                        'link_text': unicode(card),
                    } for card in [item.main_card, item.secondary_card] if card is not None]
                }))
            if len(item.all_gifted_songs):
                for song in item.all_gifted_songs:
                    extra_fields.append(('song-{}'.format(song.id), subtitledImageLink(song, _('Gift song'), 'song')))
            if len(item.all_assets):
                for asset in item.all_assets:
                    for version_name, version in models.Account.VERSIONS.items():
                        asset_image_url = getattr(asset, u'{}image_url'.format(version['prefix']), None)
                        asset_thumbnail_url = getattr(asset, u'{}image_thumbnail_url'.format(version['prefix']), None)
                        if asset_image_url:
                            field_name = '{}_{}'.format(asset.type, asset.id)
                            version_field_name = '{}{}'.format(version['prefix'], field_name)
                            image_icon = staticImageURL(asset.type_image)
                            verbose_name_subtitle = None
                            safe_verbose_name = None
                            # Translation will be what shows up on the image, show nothing
                            if models.VERSIONS_TO_LANGUAGES[version_name] == get_language():
                                pass
                            # English stamp translation
                            elif get_language() == 'en' and asset.name:
                                verbose_name_subtitle = asset.name
                                safe_verbose_name = asset.name
                            # Other languages translation when available
                            elif asset.names.get(get_language(), None):
                                verbose_name_subtitle = asset.t_name
                                safe_verbose_name = asset.t_name
                            # Other languages and likely can't speak English, show nothing
                            elif get_language() in settings.LANGUAGES_CANT_SPEAK_ENGLISH:
                                pass
                            # Other languages and available in English, show English with link to translate
                            elif asset.name:
                                verbose_name_subtitle = mark_safe(translationURL(asset.name))
                                safe_verbose_name = asset.name
                            # Song title for titles
                            if not verbose_name_subtitle and asset.song:
                                verbose_name_subtitle = mark_safe(
                                    u'<a href="{url}" data-ajax-url="{ajax_url}" class="{cls}">{title}</a>'.format(
                                        url=asset.song.item_url,
                                        ajax_url=asset.song.ajax_item_url,
                                        cls='a-nodifference',
                                        title=unicode(asset.song),
                                    ))
                                safe_verbose_name = unicode(asset.song)
                            extra_fields.append((
                                version_field_name, {
                                    'type': 'image_link',
                                    'verbose_name': _('Rare stamp') if asset.type == 'stamp' else _('Title'),
                                    'verbose_name_subtitle': verbose_name_subtitle,
                                    'icon': asset.type_icon if not image_icon else None,
                                    'image': image_icon,
                                    'value': asset_thumbnail_url if asset.type != 'title' else asset_image_url,
                                    'link': asset_image_url,
                                    'link_text': asset.names.get(
                                        models.VERSIONS_TO_LANGUAGES[version_name],
                                        safe_verbose_name or asset.name,
                                    ) if version_name != 'EN' else asset.name,
                                }))
                            orders_per_versions[version_name].append(version_field_name)
                            fields_per_version[field_name] = True
            extra_fields += add_rerun_fields(self, item, request)
            for i_version, version in enumerate(models.Account.VERSIONS.values()):
                if not getattr(item, u'{}image'.format(version['prefix'])) and getattr(item, u'{}start_date'.format(version['prefix'])):
                    extra_fields.append(('{}image'.format(version['prefix']), {
                        'image': staticImageURL(version['image'], folder='language', extension='png'),
                        'verbose_name': version['translation'],
                        'type': 'html',
                        'value': u'<hr>',
                    }))
                status = getattr(item, u'{}status'.format(version['prefix']))
                if status == 'ended':
                    extra_fields.append(('{}leaderboard'.format(version['prefix']), {
                        'icon': 'leaderboard',
                        'verbose_name': _('Leaderboard'),
                        'type': 'button',
                        'link_text': _('Open {thing}').format(thing=_('Leaderboard').lower()),
                        'value': u'/eventparticipations/?event={}&view=leaderboard&ordering=ranking&i_version={}'.format(item.id, i_version),
                        'ajax_link': u'/ajax/eventparticipations/?event={}&view=leaderboard&ordering=ranking&i_version={}&ajax_modal_only'.format(item.id, i_version),
                        'title': u'{} - {}'.format(unicode(item), _('Leaderboard')),
                    }))

            exclude_fields += ['c_versions', 'japanese_name']

            if request:
                request.fields_per_version = fields_per_version.keys()
            new_order += [_o for _l in orders_per_versions.values() for _o in _l] + EVENT_ITEM_FIELDS_ORDER_AFTER + order

            fields = super(EventCollection.ItemView, self).to_fields(
                item, *args, order=new_order, extra_fields=extra_fields, exclude_fields=exclude_fields,
                request=request, **kwargs)

            setSubField(fields, 'name', key='type', value='text' if item.t_name == item.japanese_name else 'title_text')
            setSubField(fields, 'name', key='title', value=item.t_name)
            setSubField(fields, 'name', key='value', value=item.japanese_name)

            for version in models.Account.VERSIONS.values():
                setSubField(fields, u'{}image'.format(version['prefix']), key='verbose_name', value=version['translation'])
                setSubField(fields, u'{}start_date'.format(version['prefix']), key='verbose_name', value=_('Beginning'))
                setSubField(fields, u'{}end_date'.format(version['prefix']), key='verbose_name', value=_('End'))

            if 'participations' in fields:
                setSubField(fields, 'participations', key='link', value=u'{}&view=leaderboard&ordering=id&reverse_order=on'.format(fields['participations']['link']))
                setSubField(fields, 'participations', key='ajax_link', value=u'{}&view=leaderboard&ordering=id&reverse_order=on&ajax_modal_only'.format(fields['participations']['ajax_link']))

            return fields

        def buttons_per_item(self, request, context, item):
            buttons = super(EventCollection.ItemView, self).buttons_per_item(request, context, item)
            buttons = add_rerun_buttons(self, buttons, request, item)
            return buttons

    # For AddView and EditView
    def _after_save(self, request, instance, type=None):
        if instance.main_card and instance.main_card.id:
            instance.main_card.force_update_cache('events')
        previous_main_card_id = getattr(instance, 'previous_main_card_id', None)
        if previous_main_card_id:
            previous_main_card = models.Card.objects.get(id=previous_main_card_id)
            previous_main_card.force_update_cache('events')
        if instance.secondary_card and instance.secondary_card.id:
            instance.secondary_card.force_update_cache('events')
        previous_secondary_card_id = getattr(instance, 'previous_secondary_card_id', None)
        if previous_secondary_card_id:
            previous_secondary_card = models.Card.objects.get(id=previous_secondary_card_id)
            previous_secondary_card.force_update_cache('events')
        return instance

    class AddView(MainItemCollection.AddView):
        savem2m = True
        filter_cuteform = EVENT_CUTEFORM
        ajax_callback = 'loadEventForm'

        def after_save(self, request, instance, type=None):
            instance = super(EventCollection.AddView, self).after_save(request, instance, type=type)
            return self.collection._after_save(request, instance)

    class EditView(MainItemCollection.EditView):
        savem2m = True
        filter_cuteform = EVENT_CUTEFORM
        ajax_callback = 'loadEventForm'

        def after_save(self, request, instance, type=None):
            instance = super(EventCollection.EditView, self).after_save(request, instance, type=type)
            return self.collection._after_save(request, instance)

############################################################
# Gacha Collection

GACHA_ICONS = {
    'start_date': 'date',
    'end_date': 'date',
    'english_start_date': 'date', 'english_end_date': 'date',
    'taiwanese_start_date': 'date', 'taiwanese_end_date': 'date',
    'korean_start_date': 'date', 'korean_end_date': 'date',
    'event': 'event',
    'limited': 'hourglass',
    'versions': 'world',
}

GACHA_ITEM_FIELDS_ORDER = [
    'name', 'limited',
] + [
    u'{}{}'.format(_v['prefix'], _f) for _v in models.Account.VERSIONS.values()
    for _f in models.Gacha.FIELDS_PER_VERSION
] + [
 'attribute', 'cards',
]

class GachaCollection(MainItemCollection):
    queryset = models.Gacha.objects.all()
    icon = 'scout-box'
    title = _('Gacha')
    plural_title = _('Gacha')
    form_class = forms.GachaForm
    navbar_link_list = 'girlsbandparty'
    navbar_link_list_divider_after = True
    translated_fields = ('name', )

    _gacha_type_to_cuteform = {
        'permanent': 'scout-box',
        'limited': 'hourglass',
        'dreamfes': 'music',
    }

    filter_cuteform = {
        'featured_member': {
            'to_cuteform': lambda k, v: getCharacterImageFromPk(k),
            'extra_settings': {
                'modal': 'true',
                'modal-text': 'true',
            },
        },
        'i_attribute': {},
        'event': {
            'to_cuteform': lambda k, v: v.image_url,
            'title': _('Event'),
            'extra_settings': {
                'modal': 'true',
                'modal-text': 'true',
            },
        },
        'is_limited': {
            'type': CuteFormType.OnlyNone,
        },
        'version': {
            'to_cuteform': lambda k, v: CardCollection._version_images[k],
            'image_folder': 'language',
            'transform': CuteFormTransform.ImagePath,
        },
        'gacha_type': {
            'transform': CuteFormTransform.Flaticon,
            'to_cuteform': lambda k, v: GachaCollection._gacha_type_to_cuteform[k],
        },
        'status': {
            'type': CuteFormType.HTML,
        },
    }

    share_image = justReturn('screenshots/gachas.png')
    auto_share_image = False

    def to_fields(self, view, item, in_list=False, exclude_fields=None, *args, **kwargs):
        if exclude_fields is None: exclude_fields = []
        exclude_fields.append('dreamfes')
        fields = super(GachaCollection, self).to_fields(view, item, *args, icons=GACHA_ICONS, images={
            'name': staticImageURL('gacha.png'),
            'japanese_name': staticImageURL('gacha.png'),
            'attribute': staticImageURL(item.i_attribute, folder='i_attribute', extension='png'),
            'english_image': staticImageURL('language/world.png'),
            'taiwanese_image': staticImageURL('language/zh-hant.png'),
            'korean_image': staticImageURL('language/kr.png'),
        }, exclude_fields=exclude_fields, **kwargs)
        if get_language() == 'ja' or unicode(item.t_name) == unicode(item.japanese_name):
            setSubField(fields, 'name', key='value', value=_('{} Gacha').format(item.japanese_name))
        else:
            setSubField(fields, 'name', key='type', value='title_text')
            setSubField(fields, 'name', key='title', value=_('{} Gacha').format(item.t_name))
            setSubField(fields, 'name', key='value', value=item.japanese_name + u'ガチャ')

        for version, version_details in models.Gacha.VERSIONS.items():
            setSubField(
                fields, u'{}start_date'.format(version_details['prefix']),
                key='timezones', value=[version_details['timezone'], 'Local time'],
            )
            setSubField(
                fields, u'{}end_date'.format(version_details['prefix']),
                key='timezones', value=[version_details['timezone'], 'Local time'],
            )

        if 'event' in fields:
            fields['event'] = subtitledImageLink(item.event, _('Event'), 'event')

        return fields

    class ItemView(MainItemCollection.ItemView):
        template = 'default'
        ajax_callback = 'loadEventGacha'

        def get_queryset(self, queryset, parameters, request):
            queryset = super(GachaCollection.ItemView, self).get_queryset(queryset, parameters, request)
            queryset = queryset.select_related('event').prefetch_related(
                Prefetch('cards', to_attr='all_cards'),
                Prefetch('reruns', to_attr='all_reruns'),
            )
            return queryset

        def extra_context(self, context):
            if 'js_variables' not in context:
                context['js_variables'] = {}
            context['js_variables']['versions_prefixes'] = models.Account.VERSIONS_PREFIXES
            context['js_variables']['fields_per_version'] = models.Gacha.FIELDS_PER_VERSION

        def to_fields(self, item, extra_fields=None, exclude_fields=None, order=None, request=None, *args, **kwargs):
            if extra_fields is None: extra_fields = []
            if exclude_fields is None: exclude_fields = []
            if order is None: order = []
            order = GACHA_ITEM_FIELDS_ORDER + order

            for version in models.Account.VERSIONS.values():
                start_date = getattr(item, u'{}start_date'.format(version['prefix']))
                end_date = getattr(item, u'{}end_date'.format(version['prefix']))
                image = getattr(item, u'{}image'.format(version['prefix']))

                ## Create Countdowns for Gachas that are active
                status = getattr(item, u'{}status'.format(version['prefix']))
                if status and status not in ['ended', 'invalid']:
                    extra_fields += [
                        (u'{}countdown'.format(version['prefix']), {
                            'verbose_name': _('Countdown'),
                            'value': mark_safe(toCountDown(
                                date=end_date if status == 'current' else start_date,
                                sentence=_('{time} left') if status == 'current' else _('Starts in {time}'),
                                classes=['fontx1-5'],
                            )),
                            'icon': 'times',
                            'type': 'html',
                        }),
                    ]
                ## Create image fields with placeholders when needed
                if not image and (start_date or end_date):
                    extra_fields.append(('{}image'.format(version['prefix']), {
                        'image': staticImageURL(version['image'], folder='language', extension='png'),
                        'type': 'html',
                        'value': u'<hr>',
                    }))

            # Add Image
            if item.image:
                extra_fields.append(('image', {
                    'image': staticImageURL('language/ja.png'),
                    'type': 'image',
                    'value': item.image_url,
                }))
            exclude_fields += ['japanese_name', 'c_versions']
            if len(item.all_cards):
                extra_fields.append(('cards', {
                    'icon': 'cards',
                    'verbose_name': _('Cards'),
                    'type': 'images_links',
                    'images': [{
                        'value': card.image_url,
                        'link': card.item_url,
                        'ajax_link': card.ajax_item_url,
                        'link_text': unicode(card),
                    } for card in item.all_cards],
                }))
            extra_fields += add_rerun_fields(self, item, request)
            fields = super(GachaCollection.ItemView, self).to_fields(
                item, *args, extra_fields=extra_fields, exclude_fields=exclude_fields, order=order,
                request=request, **kwargs)
            setSubField(fields, 'limited', key='verbose_name', value=_('Gacha type'))
            setSubField(fields, 'limited', key='type', value='text')
            setSubField(fields, 'limited', key='value', value=(
                _('Limited') if item.limited
                else (models.DREAMFES_PER_LANGUAGE.get(get_language(), 'Dream festival')
                      if item.dreamfes else _('Permanent'))))
            for version in models.Account.VERSIONS.values():
                setSubField(fields, u'{}image'.format(version['prefix']), key='verbose_name', value=version['translation'])
                setSubField(fields, u'{}start_date'.format(version['prefix']), key='verbose_name', value=_('Beginning'))
                setSubField(fields, u'{}end_date'.format(version['prefix']), key='verbose_name', value=_('End'))
            return fields

        def buttons_per_item(self, request, context, item):
            buttons = super(GachaCollection.ItemView, self).buttons_per_item(request, context, item)
            buttons = add_rerun_buttons(self, buttons, request, item)
            return buttons

    class ListView(MainItemCollection.ListView):
        per_line = 2
        filter_form = forms.GachaFilterForm
        ajax_callback = 'loadGachaInList'

    def _after_save(self, request, instance):
        for card in instance.cards.all():
            card.force_update_cache('gachas')
        return instance

    class AddView(MainItemCollection.AddView):
        savem2m = True

        def after_save(self, request, instance, type=None):
            return self.collection._after_save(request, instance)

    class EditView(MainItemCollection.EditView):
        savem2m = True

        def after_save(self, request, instance):
            return self.collection._after_save(request, instance)

############################################################
# Rerun gacha event

RERUN_CUTEFORM = {
    'i_version': {
        'to_cuteform': lambda k, v: AccountCollection._version_images[k],
        'image_folder': 'language',
        'transform': CuteFormTransform.ImagePath,
    },
}

class RerunCollection(MainItemCollection):
    queryset = models.Rerun.objects.all().select_related('event', 'gacha')

    filter_cuteform = RERUN_CUTEFORM
    form_class = forms.RerunForm

    class ListView(MainItemCollection.ListView):
        enabled = False

    class ItemView(MainItemCollection.ItemView):
        enabled = False

    def redirect_after_modification(self, request, item, ajax):
        if ajax:
            return (item.gacha.ajax_item_url if item.gacha
                    else (item.event.ajax_item_url if item.event
                          else '/'))
        return (item.gacha.item_url if item.gacha
                else (item.event.item_url if item.event
                      else '/'))

    class AddView(MainItemCollection.AddView):
        alert_duplicate = False
        back_to_list_button = False

        def redirect_after_add(self, *args, **kwargs):
            return self.collection.redirect_after_modification(*args, **kwargs)

    class EditView(MainItemCollection.EditView):
        back_to_list_button = False

        def redirect_after_edit(self, *args, **kwargs):
            return self.collection.redirect_after_modification(*args, **kwargs)

        def redirect_after_delete(self, *args, **kwargs):
            return self.collection.redirect_after_modification(*args, **kwargs)

############################################################
# Played songs Collection

def to_PlayedSongCollection(cls):
    _filter_cuteform = dict(_song_cuteform.items() + [
        ('full_combo', {
            'type': CuteFormType.YesNo,
        }),
        ('all_perfect', {
            'type': CuteFormType.YesNo,
        }),
        ('i_difficulty', {
            'to_cuteform': lambda k, v: models.PlayedSong.DIFFICULTY_CHOICES[k][0],
            'image_folder': 'songs',
            'transform': CuteFormTransform.ImagePath,
        }),
        ('i_version', {
            'to_cuteform': lambda k, v: AccountCollection._version_images[k],
            'image_folder': 'language',
            'transform': CuteFormTransform.ImagePath,
        }),
    ])

    class _PlayedSongCollection(cls):
        title = _('Played song')
        plural_title = _('Played songs')
        collectible_tab_name = _('Songs')
        form_class = forms.to_PlayedSongForm(cls)
        show_edit_button_superuser_only = True
        reportable = True
        report_allow_delete = False

        report_edit_templates = OrderedDict([
            ('Unrealistic Score', 'Your score is unrealistic, so we edited it. If this was a mistake, please upload a screenshot of your game to the details of your played song to prove your score and change it back. Thank you for your understanding.'),
        ])

        filter_cuteform = _filter_cuteform

        fields_icons = {
            'score': 'scoreup',
            'full_combo': 'combo',
            'all_perfect': 'combo',
            'screenshot': 'screenshot',
            'song': 'song',
        }

        fields_images = {
            'difficulty': lambda _i: _i.difficulty_image_url,
        }

        class ListView(cls.ListView):
            filter_form = forms.to_PlayedSongFilterForm(cls)
            display_style = 'table'
            display_style_table_fields = ['image', 'difficulty', 'score', 'full_combo', 'all_perfect', 'screenshot']
            show_item_buttons = True
            show_item_buttons_as_icons = True
            show_item_buttons_justified = False

            filter_cuteform = _filter_cuteform.copy()
            filter_cuteform['screenshot'] = {
                'type': CuteFormType.YesNo,
            }

            alt_views = cls.ListView.alt_views + [
                ('leaderboard', {
                    'verbose_name': _('Leaderboard'),
                    'display_style': 'row',
                    'template': 'playedSongLeaderboard',
                }),
            ]

            def get_queryset(self, queryset, parameters, request):
                queryset = super(_PlayedSongCollection.ListView, self).get_queryset(queryset, parameters, request)
                if request.GET.get('view', None) == 'leaderboard':
                    queryset = queryset.select_related('account')
                return queryset

            def table_fields(self, item, *args, **kwargs):
                fields = super(_PlayedSongCollection.ListView, self).table_fields(item, *args, **kwargs)
                setSubField(fields, 'image', key='verbose_name', value=_('Song'))
                setSubField(fields, 'image', key='type', value='image_link')
                setSubField(fields, 'image', key='link', value=item.song.item_url)
                setSubField(fields, 'image', key='link_text', value=unicode(item.song))
                setSubField(fields, 'image', key='ajax_link', value=item.song.ajax_item_url)
                setSubField(fields, 'difficulty', key='type', value='image')
                setSubField(fields, 'difficulty', key='value', value=lambda k: item.difficulty_image_url)
                setSubField(fields, 'screenshot', key='type', value='html')
                setSubField(fields, 'screenshot', key='value', value=u'<a href="{url}" target="_blank"><div class="screenshot_preview" style="background-image: url(\'{thumbnail_url}\')"></div></a>'.format(
                    url=item.screenshot_url,
                    thumbnail_url=item.screenshot_thumbnail_url,
                ) if item.screenshot else '')
                return fields

            def table_fields_headers(self, fields, view=None):
                if view is None:
                    headers = cls.__bases__[0].ListView.table_fields_headers(self, fields, view=view)
                    headers[0] = ('image', _('Image'))
                    return headers
                return []

            def extra_context(self, context):
                super(_PlayedSongCollection.ListView, self).extra_context(context)
                if context['view'] == 'leaderboard':
                    context['include_below_item'] = False
                    context['show_relevant_fields_on_ordering'] = False

    return _PlayedSongCollection

############################################################
# Songs Collection

_song_cuteform = {
    'i_band': {
        'image_folder': 'band',
        'to_cuteform': 'value',
        'title': _('Band'),
        'extra_settings': {
            'modal': 'true',
            'modal-text': 'true',
        },
    },
    'event': {
        'to_cuteform': lambda k, v: v.image_url,
        'title': _('Event'),
        'extra_settings': {
            'modal': 'true',
            'modal-text': 'true',
        },
    },
    'version': {
        'to_cuteform': lambda k, v: CardCollection._version_images[k],
        'image_folder': 'language',
        'transform': CuteFormTransform.ImagePath,
    },
}

SONG_ICONS = {
    'name': 'translate',
    'romaji_name': 'song',
    'special_band': 'rock',
    'itunes_id': 'play',
    'length': 'times',
    'unlock': 'unlock',
    'bpm': 'hp',
    'release_date': 'date',
    'event': 'event',
    'versions': 'world',
    'played': 'contest',
    'sp_notes': 'toggler'
}

SONG_ITEM_FIELDS_ORDER = ['song_name']

class SongCollection(MainItemCollection):
    queryset = models.Song.objects.all()
    title = _('Song')
    plural_title = _('Songs')
    icon = 'song'
    translated_fields = ('name', 'special_band')
    navbar_link_list = 'bangdream'

    types = {
        _unlock: {
            'title': u'Unlock - {}'.format(_info['translation']),
            'form_class': forms.unlock_to_form(_unlock),
        }
        for _unlock, _info in models.Song.UNLOCK.items()
    }

    filter_cuteform = _song_cuteform

    collectible = models.PlayedSong

    def collectible_to_class(self, model_class):
        cls = super(SongCollection, self).collectible_to_class(model_class)
        if model_class.collection_name == 'playedsong':
            return to_PlayedSongCollection(cls)
        return cls

    def to_fields(self, view, item, *args, **kwargs):
        fields = super(SongCollection, self).to_fields(
            view, item, *args, icons=SONG_ICONS, **kwargs)
        for fieldName in (
                ((['japanese_name', 'romaji_name', 'name']
                 if get_language() == 'ja' else ['romaji_name']) if view.view == 'item_view' else [])
                + ['band', 'unlock_variables', 'is_cover', 'is_full']
                + [f for f, t in models.Song.SONGWRITERS_DETAILS]
                + ((list(chain.from_iterable(
                    (u'{}_notes'.format(d), u'{}_difficulty'.format(d))
                    for d, t in models.Song.DIFFICULTIES))) if view.view == 'item_view' else [])
        ):
            if fieldName in fields:
                del(fields[fieldName])

        setSubField(fields, 'length', key='value', value=lambda f: item.length_in_minutes)
        setSubField(fields, 'unlock', key='value', value=item.unlock_sentence)

        for difficulty, verbose_name in models.Song.DIFFICULTIES:
            image = staticImageURL(difficulty, folder='songs', extension='png')
            setSubField(fields, u'{}_notes'.format(difficulty), key='image', value=image)

            diff = getattr(item, u'{}_difficulty'.format(difficulty), None)
            if diff is not None:
                setSubField(fields, u'{}_difficulty'.format(difficulty), key='image', value=image)
                setSubField(fields, u'{}_difficulty'.format(difficulty), key='type', value='html')
                setSubField(fields, u'{}_difficulty'.format(difficulty), key='value', value=mark_safe(u'{}<br />'.format(generateDifficulty(diff))))

        if item.sp_notes:
            setSubField(fields, 'special_difficulty', key='annotation', value='+ '+_('{} notes').format('SP'))
        if 'event' in fields:
            fields['event'] = subtitledImageLink(item.event, _('Event'), 'event')

        return fields

    class ListView(MainItemCollection.ListView):
        item_template = custom_item_template
        per_line = 3
        filter_form = forms.SongFilterForm
        show_collect_button = {
            'playedsong': False,
        }

        filter_cuteform = dict(_song_cuteform.items() + [
            ('is_cover', {
                'type': CuteFormType.YesNo,
            }),
            ('is_full', {
                'type': CuteFormType.YesNo,
            }),
            ('sp_notes', {
                'type': CuteFormType.YesNo,
            }),
        ])

        def extra_context(self, context):
            context['full_text'] = _('Full').upper()
            return context

    class ItemView(MainItemCollection.ItemView):
        template = 'default'
        top_illustration = 'include/songTopIllustration'
        ajax_callback = 'loadSongItem'

        def get_queryset(self, queryset, parameters, request):
            queryset = super(SongCollection.ItemView, self).get_queryset(queryset, parameters, request)
            queryset = queryset.select_related('event').prefetch_related(
                Prefetch('assets', queryset=models.Asset.objects.select_related(
                    'song').filter(c_tags__contains='cd'), to_attr='all_assets'),
                )
            return queryset

        def to_fields(self, item, extra_fields=None, exclude_fields=None, order=None, *args, **kwargs):
            if extra_fields is None: extra_fields = []
            if exclude_fields is None: exclude_fields = []
            if order is None: order = []
            exclude_fields += ['name']
            language = get_language()

            # Add title field
            title = item.japanese_name
            value = item.names.get(
                language, item.japanese_name
                if language in settings.LANGUAGES_CANT_SPEAK_ENGLISH else item.name) or title
            extra_fields.append(('song_name', {
                'verbose_name': _('Song'),
                'verbose_name_subtitle': _('Cover song') if item.is_cover else _('Original song'),
                'icon': 'id',
                'type': 'title_text' if unicode(title) != unicode(value) else 'text',
                'title': title,
                'value': value,
            }))

            order = SONG_ITEM_FIELDS_ORDER + order
            fields = super(SongCollection.ItemView, self).to_fields(
                item, *args, extra_fields=extra_fields, exclude_fields=exclude_fields, order=order, **kwargs)
            for difficulty, verbose_name in models.Song.DIFFICULTIES:
                diff_value = ''
                diff = getattr(item, u'{}_difficulty'.format(difficulty), None)
                if diff is not None:
                    diff_value = u'{}<br />'.format(generateDifficulty(diff))
                if getattr(item, u'{}_notes'.format(difficulty), None) is not None:
                    diff_value += _(u'{} notes').format(getattr(item, u'{}_notes'.format(difficulty), None))
                if diff_value != '':
                    fields[difficulty] = {
                        'verbose_name': verbose_name,
                        'type': 'html',
                        'value': mark_safe(diff_value),
                        'image': staticImageURL(difficulty, folder='songs', extension='png'),
                    }

            if 'played' in fields:
                setSubField(fields, 'played', key='link', value=u'{}&view=leaderboard&ordering=score&reverse_order=on'.format(fields['played']['link']))
                setSubField(fields, 'played', key='ajax_link', value=u'{}&view=leaderboard&ordering=score&reverse_order=on&ajax_modal_only'.format(fields['played']['ajax_link']))

            details = u''
            for fieldName, verbose_name in models.Song.SONGWRITERS_DETAILS:
                value = getattr(item, fieldName)
                if value:
                    details += u'<b>{}</b>: {}<br />'.format(verbose_name, value)
            if details:
                fields['songwriters'] = {
                    'verbose_name': _('Songwriters'),
                    'type': 'html',
                    'value': mark_safe(u'<div class="songwriters-details">{}</div>'.format(details)),
                    'icon': 'id',
                }

            # Link to Official Art with #Album cover
            if len(item.all_assets):

                # Create list of Album covers with every version showing
                song_alt_covers = []
                for _version, info in models.Account.VERSIONS.items():
                    for asset in item.all_assets:
                        if getattr(asset, '{}image_url'.format(info['prefix']), None):
                            song_alt_covers += [{
                                'value':  getattr(asset, '{}image_url'.format(info['prefix'])),
                                'link':  getattr(asset, '{}image_url'.format(info['prefix'])),
                                'link_text': unicode(asset),
                            }]

                # Create field
                # Note: song_ prefix is for css minimizing song cover size
                fields['song_alt_covers'] = {
                    'verbose_name': string_concat(_('Album cover'), ' (', _('Other'), ')'),
                    'icon': 'pictures',
                    'type': 'images_links',
                    'images': song_alt_covers,
                }

            return fields

    class AddView(MainItemCollection.AddView):
        ajax_callback = 'loadSongForm'

    class EditView(MainItemCollection.EditView):
        ajax_callback = 'loadSongForm'

        def to_translate_form_class(self):
            super(SongCollection.EditView, self).to_translate_form_class()
            self._translate_form_class = forms.to_translate_song_form_class(self._translate_form_class)

############################################################
# Collectible items Collection

def to_CollectibleItemCollection(cls):
    class _CollectibleItemCollection(cls):
        title = _('Item')
        plural_title = _('Items')

        fields_icons = {
            'quantity': 'scoreup',
            'item': 'archive',
        }

        class ListView(cls.ListView):
            item_template = 'collectibleitemItem'

        class ItemView(cls.ItemView):
            def to_fields(self, item, extra_fields=None, *args, **kwargs):
                if extra_fields is None: extra_fields = []
                if item.item.i_type:
                    extra_fields.append(('type', {
                        'verbose_name': _('Type'),
                        'value': item.item.t_type,
                        'icon': 'category',
                    }))
                extra_fields.append((
                    'item_details', {
                        'verbose_name': item.item.t_name,
                        'value': (False, item.item.t_m_description if item.item.m_description else ''),
                        'type': 'markdown',
                        'icon': 'present',
                    }))
                fields = super(_CollectibleItemCollection.ItemView, self).to_fields(
                    item, *args, extra_fields=extra_fields, **kwargs)
                return fields

        class AddView(cls.AddView):
            unique_per_owner = True

    return _CollectibleItemCollection

############################################################
# Items Collection

class ItemCollection(MainItemCollection):
    title = _('Item')
    plural_title = _('Items')
    queryset = models.Item.objects.all()
    translated_fields = ('name', 'm_description', )
    icon = 'archive'
    navbar_link_list = 'girlsbandparty'
    collectible = models.CollectibleItem

    def collectible_to_class(self, model_class):
        cls = super(ItemCollection, self).collectible_to_class(model_class)
        return to_CollectibleItemCollection(cls)

    def buttons_per_item(self, view, request, context, item):
        buttons = super(ItemCollection, self).buttons_per_item(view, request, context, item)
        if 'collectibleitem' in buttons:
            buttons['collectibleitem']['title'] = _(u'Edit your {thing}').format(thing=unicode(item).lower())
        return buttons

    def get_title_prefixes(self, request, context):
        title_prefixes = super(ItemCollection, self).get_title_prefixes(request, context)
        title_prefixes.append({
            'title': _('Gallery'),
            'url': '/gallery/',
        })
        return title_prefixes

    class ListView(MainItemCollection.ListView):
        ajax_item_popover = True
        per_line = 4
        filter_form = forms.ItemFilterForm
        hide_sidebar = True

    class ItemView(MainItemCollection.ItemView):
        comments_enabled = False
        share_enabled = False

        def to_fields(self, item, only_fields=None, *args, **kwargs):
            if not only_fields:
                only_fields = ['i_type', 'm_description']
            fields = super(ItemCollection.ItemView, self).to_fields(item, *args,
                only_fields=only_fields, icons={'type': 'category', 'description': 'present',}, **kwargs)
            setSubField(fields, 'description', key='verbose_name', value=unicode(item))
            return fields

############################################################
# Areas Collection

class AreaCollection(MainItemCollection):
    title = _('Location')
    plural_title = _('Locations')
    queryset = models.Area.objects.all()
    translated_fields = ('name', )
    icon = 'world'
    navbar_link_list = 'girlsbandparty'
    navbar_link_title = property(lambda _s: _('{things} list').format(things=_('Area items')))

    def get_title_prefixes(self, request, context):
        title_prefixes = super(AreaCollection, self).get_title_prefixes(request, context)
        title_prefixes.append({
            'title': _('Gallery'),
            'url': '/gallery/',
        })
        return title_prefixes

    class ListView(MainItemCollection.ListView):
        before_template = 'include/beforeAreas'
        after_template = 'include/afterAreas'
        per_line = 3
        item_template = custom_item_template

        def get_page_title(self):
            return _('{things} list').format(things=_('Area items'))

        def extra_context(self, context):
            super(AreaCollection.ListView, self).extra_context(context)
            context['area_items_sentence'] = _('View all')

    class ItemView(MainItemCollection.ItemView):
        enabled = False

############################################################
# Collectible area items Collection

_AREAS_IMAGES = { area['id']: area['image'] for area in getattr(django_settings, 'AREAS', []) }

AREA_ITEM_CUTEFORM = {
    'area': {
        'to_cuteform': lambda k, v: _AREAS_IMAGES[k],
    },
    'band': {
        'image_folder': 'band',
        'to_cuteform': 'value',
        'title': _('Band'),
        'extra_settings': {
            'modal': 'true',
            'modal-text': 'true',
        },
    },
    'i_attribute': {},
    'i_boost_stat': {
        'type': CuteFormType.HTML,
        'to_cuteform': lambda k, v: format_html(
            u'<span data-toggle="tooltip" title="{}">{}</div>', unicode(v), v[0]),
    },
}

COLLECTIBLEAREAITEM_CUTEFORM = {
    'area': {
        'to_cuteform': lambda k, v: _AREAS_IMAGES[k],
    },
    'i_attribute': {},
}
memberBandMergeCuteForm(COLLECTIBLEAREAITEM_CUTEFORM)

def to_CollectibleAreaItemCollection(cls):
    class _CollectibleAreaItemCollection(cls):
        title = _('Area item')
        plural_title = _('Area items')
        form_class = forms.to_CollectibleAreaItemForm(cls)
        filter_cuteform = AREA_ITEM_CUTEFORM

        fields_icons = {
            'level': 'scoreup',
            'areaitem': 'town',
        }

        class ListView(cls.ListView):
            item_template = 'collectibleitemItem'
            filter_form = forms.to_CollectibleAreaItemFilterForm(cls)

        class ItemView(cls.ItemView):
            def to_fields(self, item, extra_fields=None, *args, **kwargs):
                if extra_fields is None: extra_fields = []
                if item.areaitem.type:
                    extra_fields.append(('type', {
                        'verbose_name': _('Area'),
                        'value': (
                            item.areaitem.t_type if not item.areaitem.instrument
                            else string_concat(item.areaitem.t_type, ' (', item.areaitem.t_instrument, ')')),
                        'icon': 'pinpoint',
                    }))
                extra_fields.append((
                    'item_details', {
                        'verbose_name': item.formatted_name,
                        'value': item.formatted_description,
                        'type': 'long_text',
                        'icon': 'fountain',
                    },
                ))
                fields = super(_CollectibleAreaItemCollection.ItemView, self).to_fields(
                    item, *args, extra_fields=extra_fields, **kwargs)
                return fields

        class AddView(cls.AddView):
            unique_per_owner = True
            add_to_collection_variables = cls.AddView.add_to_collection_variables + [
                'max_level',
            ]

    return _CollectibleAreaItemCollection

############################################################
# Area items Collection

class AreaItemCollection(MainItemCollection):
    title = _('Area item')
    plural_title = _('Area items')
    queryset = models.AreaItem.objects.all()
    translated_fields = ('name', 'about')
    icon = 'town'
    navbar_link = False
    filter_cuteform = AREA_ITEM_CUTEFORM

    collectible = models.CollectibleAreaItem

    def collectible_to_class(self, model_class):
        cls = super(AreaItemCollection, self).collectible_to_class(model_class)
        return to_CollectibleAreaItemCollection(cls)

    def get_title_prefixes(self, request, context):
        title_prefixes = super(AreaItemCollection, self).get_title_prefixes(request, context)
        title_prefixes += [
            {
                'title': _('Girls Band Party'),
                'url': '/girlsbandparty/',
            },
            {
                'title': _('Gallery'),
                'url': '/gallery/',
            },
            {
                'title': _('{things} list').format(things=_('Area items')),
                'url': '/areas/',
            },
        ]
        return title_prefixes

    class ListView(MainItemCollection.ListView):
        filter_form = forms.AreaItemFilterForm
        ajax_item_popover = True
        item_template = custom_item_template

        def get_h1_title(self, *args, **kwargs):
            title_prefixes, h1 = super(AreaItemCollection.ListView, self).get_h1_title(*args, **kwargs)
            h1['title'] = _('View all')
            return title_prefixes, h1

        def extra_context(self, context):
            super(AreaItemCollection.ListView, self).extra_context(context)
            context['level_1_sentence'] = _('Level {level}').format(level=1)

    class ItemView(MainItemCollection.ItemView):
        comments_enabled = False
        share_enabled = False

        def get_h1_title(self, request, context, *args, **kwargs):
            title_prefixes, h1 = super(AreaItemCollection.ItemView, self).get_h1_title(
                request, context, *args, **kwargs)
            # Avoid adding link to list of all items, encourage to go back to area list
            title_prefixes = self.collection.get_title_prefixes(request, context)
            return title_prefixes, h1

        def to_fields(self, item, *args, **kwargs):
            fields = []
            if item.type:
               fields += [('type', {
                    'verbose_name': _('Area'),
                    'value': item.t_type if not item.instrument else string_concat(item.t_type, ' (', item.t_instrument, ')'),
                    'icon': 'pinpoint',
                })]
            fields += [('item_details', {
                'verbose_name': item.formatted_name,
                'value': item.formatted_description,
                'type': 'long_text',
                'icon': 'fountain',
            })]
            if item.about:
                fields += [('about', {
                    'verbose_name': _('About'),
                    'value': item.t_about,
                    'type': 'long_text',
                    'icon': 'author',
                })]
            fields = OrderedDict(fields)
            return fields

############################################################
# Assets Collection

ASSET_CUTEFORM = {
    'i_band': {
        'image_folder': 'band',
        'to_cuteform': 'value',
        'title': _('Band'),
        'extra_settings': {
            'modal': 'true',
            'modal-text': 'true',
        },
    },
    'member_band': {
        'to_cuteform': lambda k, v: (
            getCharacterImageFromPk(int(k[7:]))
            if k.startswith('member-')
            else staticImageURL(v, folder='band', extension='png')
        ),
        'title': string_concat(_('Member'), ' / ', _('Band')),
        'extra_settings': {
            'modal': 'true',
            'modal-text': 'true',
        },
    },
    'i_version': {
        'to_cuteform': lambda k, v: AccountCollection._version_images[k],
        'image_folder': 'language',
        'transform': CuteFormTransform.ImagePath,
    },
    'event': {
        'to_cuteform': lambda k, v: v.image_url,
        'title': _('Event'),
        'extra_settings': {
            'modal': 'true',
            'modal-text': 'true',
        },
    },
    'value': {
        'type': CuteFormType.HTML,
    },
    'is_event': {
        'type': CuteFormType.YesNo,
    },
    'is_song': {
        'type': CuteFormType.YesNo,
    },
}

ASSET_CUTEFORM_LIST = ASSET_CUTEFORM.copy()
ASSET_CUTEFORM_LIST['members'] = {
    'to_cuteform': lambda k, v: getCharacterImageFromPk(k),
    'extra_settings': {
        'modal': 'true',
        'modal-text': 'true',
    }
}

ASSET_ORDER = ['name', 'type'] + [
    u'{}image'.format(_v['prefix']) for _v in models.Account.VERSIONS.values()
] + ['i_band', 'members', 'event', 'song', 'source']

ASSET_ICONS = {
    'name': 'album', 'type': 'category', 'source': 'about',
    'event': 'event', 'song': 'song',
}

class AssetCollection(MainItemCollection):
    title = _('Asset')
    plural_title = _('Assets')
    queryset = models.Asset.objects.all()
    translated_fields = ('name', )
    icon = 'pictures'
    navbar_link = False
    filter_cuteform = ASSET_CUTEFORM

    types = {
        _type: {
            'title': _info['translation'],
            'form_class': forms.asset_type_to_form(_type),
        }
        for _type, _info in models.Asset.TYPES.items()
    }

    def _preselect_based_on_type(self, queryset, request, variable, prefetch=False):
        if not request.GET.get('i_type', None) or int(request.GET.get('i_type')) in [
                i for i, (type_name, type) in enumerate(models.Asset.TYPES.items())
                if variable in type['variables']]:
            if prefetch:
                return queryset.prefetch_related(Prefetch(variable, to_attr=u'all_{}'.format(variable)))
            else:
                return queryset.select_related(variable)
        return queryset

    def get_queryset(self, queryset, parameters, request):
        queryset = super(AssetCollection, self).get_queryset(queryset, parameters, request)
        queryset = self._preselect_based_on_type(queryset, request, 'event')
        queryset = self._preselect_based_on_type(queryset, request, 'song')
        queryset = self._preselect_based_on_type(queryset, request, 'members', prefetch=True)
        return queryset

    def to_fields(self, view, item, extra_fields=None, exclude_fields=None, order=None, icons=None, *args, **kwargs):
        if extra_fields is None: extra_fields = []
        if exclude_fields is None: exclude_fields = []
        if icons is None: icons = {}
        icons.update(ASSET_ICONS)
        exclude_fields += ['c_tags', 'value', 'source_link']
        if not order:
            order = ASSET_ORDER

        # Images
        for _version, _info in models.Account.VERSIONS.items():
            if getattr(item, '{}image'.format(_info['prefix'])):
                # If official art is version-less, generate version-less style
                if getattr(item, 'type')=='officialart' and getattr(item, 'value')==0:
                    extra_fields.append(('{}image'.format(_info['prefix']), {
                        'icon': 'download',
                        'link': getattr(item, '{}image_url'.format(_info['prefix'])),
                        'link_text': _('Image'),
                        'verbose_name': _('Image'),
                        'value': getattr(item, '{}image_thumbnail_url'.format(_info['prefix'])),
                        'type': 'image_link',
                    }))
                else:
                    extra_fields.append(('{}image'.format(_info['prefix']), {
                        'image': staticImageURL('language/{}.png'.format(_info['image'])),
                        'link': getattr(item, '{}image_url'.format(_info['prefix'])),
                        'link_text': string_concat(_('Image'), ' (', _info['translation'], ')'),
                        'verbose_name': _('Image'),
                        'verbose_name_subtitle': _info['translation'],
                        'value': getattr(item, '{}image_thumbnail_url'.format(_info['prefix'])),
                        'type': 'image_link',
                    }))

        # Song + Event
        for _field, _tl in [('song', _('Song')), ('event', _('Event'))]:
            if getattr(item, _field):
                 extra_fields.append((_field, subtitledImageLink(getattr(item, _field), _tl, _field)))

        fields = super(AssetCollection, self).to_fields(view, item, *args, icons=icons, images={
            'image': staticImageURL('language/ja.png'),
            'english_image': staticImageURL('language/world.png'),
            'taiwanese_image': staticImageURL('language/zh-hant.png'),
            'korean_image': staticImageURL('language/kr.png'),
        }, extra_fields=extra_fields, exclude_fields=exclude_fields, order=order, **kwargs)

        if 'band' in fields:
            fields['band'] = bandField(item.band, item.i_band)

        for field, verbose_name in [('song', _('Song')), ('event', _('Event'))]:
            if field in fields:
                 fields[field] = subtitledImageLink(getattr(item, field), verbose_name, field)

        if item.type is 'title' and item.value:
            setSubField(fields, 'name', key='value', value=string_concat(item.t_name, ' ', item.value))

        if item.source and item.source_link:
            setSubField(fields, 'source', key='type', value='link')
            setSubField(fields, 'source', key='value', value=item.source_link)
            setSubField(fields, 'source', key='icon', value='link')
            setSubField(fields, 'source', key='link_text', value=item.source)

        # Tags
        setSubField(fields, 'type', key='type', value='html')
        setSubField(fields, 'type', key='value', value=(
            lambda f: u'{}<ul>{}</ul>'.format(
                item.t_type,
                u''.join([
                    u'<li><a href="/assets/?c_tags={tag}" data-ajax-url="/ajax/assets/?c_tags={tag}&ajax_modal_only" data-ajax-title="{assets} - {verbose_name}">#{verbose_name}</a></li>'.format(
                        tag=tag,
                        verbose_name=verbose_name,
                        assets=_('Assets'),
                    ) for tag, verbose_name in item.t_tags.items()
                ]))))

        # Use correct translation for each asset in alt of image
        for version_name, version in models.Account.VERSIONS.items():
            setSubField(fields, u'{}image'.format(version['prefix']), key='image_text',
                value=item.names.get(models.VERSIONS_TO_LANGUAGES.get(version_name, None), item.name))
        return fields

    def _get_title_prefixes_based_on_item_type(self, type=None):
        if type in ['comic', 'officialart']:
            return [
                {
                    'title': _('BanG Dream!'),
                    'url': '/bangdream/',
                },
            ]
        return [
            {
                'title': _('Girls Band Party'),
                'url': '/girlsbandparty/',
            },
            {
                'title': _('Gallery'),
                'url': '/gallery/',
            },
        ]

    class ItemView(MainItemCollection.ItemView):
        def to_fields(self, item, extra_fields=None, preselected=None, *args, **kwargs):
            if not extra_fields: extra_fields = []
            if not preselected: preselected = []
            preselected += ['event', 'song']
            if getattr(item, 'all_members', []):
                extra_fields.append(('members', {
                    'icon': 'users',
                    'verbose_name': _('Members'),
                    'type': 'images_links',
                    'images': [{
                        'value': member.square_image_url,
                        'link': member.item_url,
                        'ajax_link': member.ajax_item_url,
                        'link_text': unicode(member),
                    } for member in item.all_members]
                }))
            fields = super(AssetCollection.ItemView, self).to_fields(
                item, *args, extra_fields=extra_fields, preselected=preselected, **kwargs)
            return fields

        def get_h1_title(self, request, context, item):
            _unused_title_prefixes, h1 = super(AssetCollection.ItemView, self).get_h1_title(
                request, context, item)
            title_prefixes = self.collection._get_title_prefixes_based_on_item_type(type=item.type)
            title_prefixes.append({
                'title': _('{things} list').format(things=item.t_type),
                'url': self.collection.get_list_url(preset=item.type),
            })
            return title_prefixes, h1

    class ListView(MainItemCollection.ListView):
        filter_form = forms.AssetFilterForm
        filter_cuteform = ASSET_CUTEFORM_LIST
        per_line = 5
        page_size = 25
        item_padding = None
        show_items_names = True

        def top_buttons(self, request, context):
            buttons = super(AssetCollection.ListView, self).top_buttons(request, context)
            if request.GET.get('i_type', None) or context.get('preset', None):
                return OrderedDict([
                    (key, value)
                    for key, value in buttons.items()
                    if (not key.startswith('add_')
                        or key == u'add_{}'.format(
                            models.Asset.get_reverse_i('type', int(request.GET.get('i_type', None)))
                            if request.GET.get('i_type', None)
                            else context['preset'],
                        ))
                ])
            return buttons

        def get_h1_title(self, request, context, view=None, preset=None):
            _unused_title_prefixes, h1 = super(AssetCollection.ListView, self).get_h1_title(
                request, context, view=view, preset=preset)

            i_type = context['request'].GET.get('i_type', None)
            if i_type:
                preset = models.Asset.get_reverse_i('type', int(i_type))

            if preset:
                type = preset.split('-')[0] if '-' in preset else preset
                i_type = models.Asset.get_i('type', type)
                title_prefixes = self.collection._get_title_prefixes_based_on_item_type(type)
                type_title = _('{things} list').format(things=models.Asset.get_verbose_i('type', i_type))

                if '-' in preset:
                    title_prefixes.append({
                        'title': type_title,
                        'url': self.collection.get_list_url(preset=type),
                    })
                else:
                    h1['title'] = type_title

            else:
                title_prefixes = self.collection._get_title_prefixes_based_on_item_type(type=None)

            return title_prefixes, h1

    class AddView(MainItemCollection.AddView):
        savem2m = True

    class EditView(MainItemCollection.EditView):
        savem2m = True

COSTUME_CUTEFORM = {
    'i_costume_type': {
        'type': CuteFormType.HTML,
    },
    'card': {
        'to_cuteform': lambda k, v: v.image_url,
        'title': _('Card'),
        'extra_settings': {
            'modal': 'true',
            'modal-text': 'true',
        },
    },
    'member': {
        'to_cuteform': lambda k, v: (getCharacterImageFromPk(k) if k != forms.CostumeFilterForm.ID_OF_MISC_MEMBERS
            else staticImageURL('i_misc_member.png')),
        'title': _('Member'),
        'extra_settings': {
            'modal': 'true',
            'modal-text': 'true',
        },
    },
    'i_band': {
        'image_folder': 'band',
        'to_cuteform': 'value',
        'title': _('Band'),
        'extra_settings': {
            'modal': 'true',
            'modal-text': 'true',
        },
    },
    'i_rarity': {
        'type': CuteFormType.HTML,
        'to_cuteform': lambda k, v: rarity_to_stars_images(k),
    },
    'version': {
        'to_cuteform': lambda k, v: CardCollection._version_images[k],
        'image_folder': 'language',
        'transform': CuteFormTransform.ImagePath,
    },
}

class CostumeCollection(MainItemCollection):
    queryset = models.Costume.objects.select_related('card', 'member')
    title = _('Costume')
    plural_title = _('Costumes')
    icon = 'dress'
    translated_fields = ('name',)
    navbar_link_list = 'girlsbandparty'
    navbar_link_list_divider_after = True
    form_class = forms.CostumeForm
    filter_cuteform = COSTUME_CUTEFORM

    def to_fields(self, view, item, extra_fields=None, exclude_fields=None, *args, **kwargs):
        extra_fields = extra_fields or []
        exclude_fields = exclude_fields or []
        # these are all redundant with the viewer + extra field below
        exclude_fields.extend(['i_costume_type', 'image', 'model_pkg', 'name'])

        if item.card:
            extra_fields.append(('card', {
                'verbose_name': _('Card'),
                'type': 'text_with_link',
                'value': unicode(item.card),
                'ajax_link': item.card.ajax_item_url,
                'link': item.card.item_url,
                'link_text': _('Open {thing}').format(thing=unicode(_('Card')).lower()),
                'icon': 'album',
                'image': item.card.image_trained_url or item.card.image_url,
            }))
        else:
            member_field_params = {
                'verbose_name': _('Costume'),
                'type': 'text',
                'value': unicode(item.t_name),
                'icon': 'profile',
            }
            if item.member:
                member_field_params.update({
                    'type': 'text_with_link',
                    'ajax_link': item.member.ajax_item_url,
                    'link': item.member.item_url,
                    'link_text': unicode(item.member),
                    'image': item.member.square_image_url,
                })
            extra_fields.append(('costume', member_field_params))

        if item.chibis:
            extra_fields.append(('chibis', {
                'icon': 'pictures',
                'type': 'images_links',
                'verbose_name': _('Chibi'),
                'images': [{
                    'value': chibi.image_url,
                    'link': chibi.image_original_url,
                    'link_text': u'{} - {}'.format(unicode(item), _('Chibi')),
                    'verbose_name': _('Chibi'),
                } for chibi in item.chibis],
            }))

        fields = super(CostumeCollection, self).to_fields(view, item, extra_fields=extra_fields, exclude_fields=exclude_fields, *args, **kwargs)
        return fields

    def buttons_per_item(self, view, request, context, item):
        buttons = super(CostumeCollection, self).buttons_per_item(view, request, context, item)

        # Card-associated costumes take their name from the card, so you can't translate them.
        if 'translate' in buttons and item.card:
            del buttons['translate']

        return buttons

    class ListView(MainItemCollection.ListView):
        item_template = custom_item_template
        per_line = 4
        filter_form = forms.CostumeFilterForm
        # not with 4 to a row
        show_relevant_fields_on_ordering = False

        alt_views = MainItemCollection.ListView.alt_views + [
            ('chibis', {
                'verbose_name': _('Chibis'),
                'per_line': 2,
            }),
        ]

        def get_queryset(self, queryset, parameters, request):
            queryset = super(CostumeCollection.ListView, self).get_queryset(queryset, parameters, request)
            if parameters.get('view') == 'chibis':
                return queryset.filter(owned_chibis__isnull=False).distinct().prefetch_related(
                    Prefetch('owned_chibis', to_attr='chibis'))
            else:
                return queryset.filter(model_pkg__isnull=False).exclude(model_pkg='')

        def to_fields(self, item, *args, **kwargs):
            fields = super(CostumeCollection.ListView, self).to_fields(item, *args, **kwargs)
            return fields

    class ItemView(MainItemCollection.ItemView):
        top_illustration = 'include/costumeTopIllustration'
        js_files = LIVE2D_JS_FILES
        ajax_callback = 'loadModelViewerAjax'
        show_item_buttons = False
        item_padding = 0

        def extra_context(self, context):
            # the old modal JS loading workaround
            if context['request'].path_info.startswith('/ajax/'):
                is_ajax = True
                context['late_js_files'] = context['js_files']
                context['js_files'] = []
                context['danger_zone'] = 220
            else:
                is_ajax = False
                context['danger_zone'] = 100

            if context['request'].GET.get('from_card') is not None:
                # try to simulate the big back link in the previous live2d page
                # only the actual link can be clicked though, unfortunately
                setSubField(context['item_fields'], 'card', key='icon', value='back')

            if not is_ajax:
                # disable AJAX on standalone viewer pages, as having two viewers open at once will cause trouble
                setSubField(context['item_fields'], 'card', key='ajax_link', value=None)
                setSubField(context['item_fields'], 'costume', key='ajax_link', value=None)

            return context

        def get_queryset(self, queryset, parameters, request):
            queryset = super(CostumeCollection.ItemView, self).get_queryset(queryset, parameters, request)
            queryset = queryset.select_related('card', 'member').prefetch_related(
                Prefetch('owned_chibis', to_attr='chibis'))
            return queryset
