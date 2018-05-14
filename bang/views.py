from django.utils.translation import ugettext_lazy as _
from django.utils.safestring import mark_safe
from django.shortcuts import render, redirect
from django.conf import settings as django_settings
from magi.utils import getGlobalContext, ajaxContext, redirectWhenNotAuthenticated, cuteFormFieldsForContext, CuteFormTransform, get_one_object_or_404
from magi.item_model import get_image_url_from_path
from magi.views import indexExtraContext
from bang.constants import LIVE2D_JS_FILES
from bang.magicollections import CardCollection
from bang.forms import TeamBuilderForm
from bang.models import Card

def live2d(request, pk, slug=None):
    ajax = request.path_info.startswith('/ajax/')
    context = ajaxContext(request) if ajax else getGlobalContext(request)
    context['ajax'] = ajax

    queryset = Card.objects.filter(id=pk, live2d_model_pkg__isnull=False)
    the_card = get_one_object_or_404(queryset)

    context['page_title'] = u'{}: {}'.format('Live2D', unicode(the_card))
    context['item'] = the_card
    context['package_url'] = get_image_url_from_path(the_card.live2d_model_pkg)

    # Work around jQuery behaviour; details in pages/live2dviewer.html.
    if ajax:
        context['late_js_files'] = LIVE2D_JS_FILES
        context['danger_zone'] = 220
    else:
        context['js_files'] = LIVE2D_JS_FILES
        context['danger_zone'] = 100

    context['extends'] = 'base.html' if not context['ajax'] else 'ajax.html'
    context['canvas_size'] = (562, 562) if context['ajax'] else (1334, 1000)

    return render(request, 'pages/live2dviewer.html', context)

SKILL_TYPE_TO_MAIN_VALUE = {
    '1': 'skill_percentage', # score up
    '2': 'skill_stamina', # life recovery
    '3': '5 - i_skill_note_type', # perfect lock, BAD = 1, GOOD = 2, GREAT = 3
}

def teambuilder(request):
    context = getGlobalContext(request)

    redirectWhenNotAuthenticated(request, context, next_title=_('Team builder'))
    context['page_title'] = _('Team builder')
    context['side_bar_no_padding'] = True

    if len(request.GET) > 0:
        form = TeamBuilderForm(request.GET, request=request)
        if form.is_valid():
            extra_select = {
                'is_correct_band': u'i_band = {}'.format(form.cleaned_data['i_band']),
                'is_correct_attribute': u'i_attribute = {}'.format(form.cleaned_data['i_attribute']),
                'overall_stats': u'CASE trained WHEN 1 THEN performance_trained_max + technique_trained_max + visual_trained_max ELSE performance_max + technique_max + visual_max END',
            }
            order_by = [
                '-is_correct_band',
                '-is_correct_attribute',
            ]
            if form.cleaned_data['i_skill_type']:
                extra_select['is_correct_skill'] = u'i_skill_type = {}'.format(form.cleaned_data['i_skill_type'])
                extra_select['skill_real_duration'] = u'skill_duration + ((IFNULL(skill_level, 1) - 1) * 0.5)'
                extra_select['skill_main_value'] = SKILL_TYPE_TO_MAIN_VALUE[form.cleaned_data['i_skill_type']]
                extra_select['skill_significant_value'] = u'({}) * ({})'.format(extra_select['skill_real_duration'], extra_select['skill_main_value'])
                order_by += ['-is_correct_skill', '-skill_significant_value']
            order_by += ['-overall_stats']
            queryset = form.Meta.model.objects.extra(select=extra_select).order_by(*order_by).select_related('card', 'card__member')
            queryset = form.filter_queryset(queryset, request.GET, request)

            # Only allow one of each member per team
            added_members = []
            team = []
            for cc in queryset:
                cc.calculation_details = [
                    unicode(cc.card),
                    u'Skill type: {}'.format(unicode(cc.card.t_skill_type)),
                    'Skill: {}'.format(cc.card.full_skill),
                    'Base skill duration: {}'.format(cc.card.skill_duration),
                    'Skill level: {}'.format(cc.skill_level or 1),

                    mark_safe(u'Real skill duration: {}<br><small class="text-muted">skill_duration + (skill_level - 1) * 0.5)</small>'.format(cc.skill_real_duration)),
                    mark_safe(u'Main value of skill: {}<br><small class="text-muted">{}</small>'.format(
                        cc.skill_main_value,
                        SKILL_TYPE_TO_MAIN_VALUE[form.cleaned_data['i_skill_type']])
                    ),
                    mark_safe(u'Significant value (for calculation): {}<br><small class="text-muted">real_skill_duration * main_value</small>'.format(cc.skill_significant_value),),
                ]
                if cc.card.member_id in added_members:
                    continue
                team.append(cc)
                added_members.append(cc.card.member_id)
                if len(team) == 5:
                    break

            context['team'] = team
        else:
            context['hide_side_bar'] = True
    else:
        form = TeamBuilderForm(request=request)
        context['hide_side_bar'] = True

    cuteFormFieldsForContext({
        'i_band': {
            'image_folder': 'band',
            'to_cuteform': 'value',
            'extra_settings': {
                'modal': 'true',
                'modal-text': 'true',
            },
        },
        'i_attribute': {},
        'i_skill_type': {
            'to_cuteform': lambda k, v: CardCollection._skill_icons[k],
            'transform': CuteFormTransform.Flaticon,
        },
    }, context, form=form, prefix='#teambuilder-form ')

    context['filter_form'] = form
    return render(request, 'pages/teambuilder.html', context)
