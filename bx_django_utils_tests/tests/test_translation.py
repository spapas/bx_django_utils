import json
import re
from itertools import product

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import translation

from bx_django_utils.models.manipulate import FieldUpdate, create_or_update2
from bx_django_utils.test_utils.users import make_test_user
from bx_django_utils.translation import FieldTranslation, create_or_update_translation_callback
from bx_django_utils_tests.test_app.models import TranslatedModel


class TranslationFieldTestCase(TestCase):
    def test_stores_only_wanted_languages(self):
        obj = TranslatedModel(
            translated={'de-de': 'Hallo', 'en-us': 'Hello', 'es': 'Hola', 'it': 'Ciao'},
            translated_multiline={'de-de': 'Hallo'},
        )
        with self.assertRaisesMessage(ValidationError, 'Unknown translation language(s): it'):
            obj.full_clean()

        obj = TranslatedModel(
            translated={'de-de': 'Hallo'},
            translated_multiline={'de-de': 'Hallo', 'en-us': 'Hello', 'es': 'Hola', 'it-it': 'Ciao', 'xx': 'foo'},
        )
        with self.assertRaisesMessage(ValidationError, 'Unknown translation language(s): it-it, xx'):
            obj.full_clean()

    def test_field_translation(self):
        translated = FieldTranslation()
        self.assertEqual(translated.get_first([1, 2, 3]), FieldTranslation.UNTRANSLATED)
        self.assertEqual(repr(translated), 'FieldTranslation({})')

        translated = FieldTranslation({'de-de': 'Hallo'})
        self.assertEqual(repr(translated), "FieldTranslation({'de-de': 'Hallo'})")
        self.assertEqual(translated.get_first(['foo', 'bar', 'en-gb', 'de-de']), 'Hallo')

        obj1 = TranslatedModel.objects.create(translated={'de-de': 'Hallo 1', 'en-us': 'Hello 1'})
        obj1.full_clean()
        self.assertEqual(repr(obj1.translated), "FieldTranslation({'de-de': 'Hallo 1', 'en-us': 'Hello 1'})")

        obj2 = TranslatedModel.objects.create(translated={'de-de': 'Hallo 2', 'en-us': 'Hello 2'})
        obj2.full_clean()

        self.assertNotEqual(obj1.translated, obj2.translated)

        qs = TranslatedModel.objects.order_by('translated').values('translated')
        self.assertQuerysetEqual(
            qs,
            [
                {'translated': FieldTranslation({'de-de': 'Hallo 1', 'en-us': 'Hello 1'})},
                {'translated': FieldTranslation({'de-de': 'Hallo 2', 'en-us': 'Hello 2'})},
            ],
        )

    def test_create_or_update(self):
        # Create via create_or_update2():
        result = create_or_update2(ModelClass=TranslatedModel, translated={'de-de': 'Hallo'})
        self.assertTrue(result.created)
        instance = result.instance
        self.assertEqual(instance.translated, {'de-de': 'Hallo'})

        # Update existing entry:
        result = create_or_update2(
            ModelClass=TranslatedModel,
            lookup=dict(pk=instance.pk),
            translated={'de-de': 'Hallo', 'en-us': 'Hello'},
        )
        self.assertFalse(result.created)  # updated?
        instance = result.instance
        self.assertEqual(result.updated_fields, ['translated'])
        self.assertEqual(
            result.update_info,
            [
                FieldUpdate(
                    field_name='translated',
                    old_value=FieldTranslation({'de-de': 'Hallo'}),
                    new_value={'de-de': 'Hallo', 'en-us': 'Hello'},
                )
            ],
        )
        self.assertEqual(instance.translated, {'de-de': 'Hallo', 'en-us': 'Hello'})

        # We have a special callback to avoid deleting translations:
        result = create_or_update2(
            ModelClass=TranslatedModel,
            lookup=dict(pk=instance.pk),
            update_model_field_callback=create_or_update_translation_callback,
            translated={'de-de': 'Hallo !', 'es': 'Hola'},
        )
        self.assertFalse(result.created)  # updated?
        instance = result.instance
        self.assertEqual(result.updated_fields, ['translated'])
        self.assertEqual(
            result.update_info,
            [
                FieldUpdate(
                    field_name='translated',
                    old_value=FieldTranslation({'de-de': 'Hallo', 'en-us': 'Hello'}),
                    new_value={'de-de': 'Hallo !', 'en-us': 'Hello', 'es': 'Hola'},
                )
            ],
        )
        self.assertEqual(
            instance.translated,
            FieldTranslation(
                {
                    'de-de': 'Hallo !',  # <<< changed
                    'en-us': 'Hello',  # <<< untouched
                    'es': 'Hola',  # <<< added
                }
            ),
        )


class TranslationAdminTestCase(TestCase):
    # test admin base class and widgets

    def setUp(self):
        super().setUp()
        self.user = make_test_user(is_superuser=True)
        self.obj = TranslatedModel(
            translated={'de-de': 'Zug', 'en-us': 'Train', 'es': 'Tren'},
            translated_multiline={
                'de-de': 'Ein Zug ist sehr schnell.\nZüge können schneller sein als Autos.',
                'en-us': 'A train is very fast.\nTrains can be faster than cars.',
                'es': 'Un tren es muy rápido.\nLos trenes pueden ser más rápidos que los automóviles.',
            },
        )
        self.obj.full_clean()
        self.obj.save()
        self.client.force_login(self.user)

    def test_changelist(self):
        CODE = 'de-de'
        with translation.override(CODE):
            response = self.client.get('/admin/test_app/translatedmodel/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'text/html; charset=utf-8')
        response_content = response.content.decode()
        self.assertIn('class="field-get_translated"', response_content)
        self.assertInHTML(self.obj.translated[CODE], response_content)
        self.assertIn('class="field-get_translated_multiline"', response_content)
        self.assertInHTML(self.obj.translated_multiline[CODE], response_content)

    def test_change(self):
        # view existing record's change form
        response = self.client.get(f'/admin/test_app/translatedmodel/{self.obj.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'text/html; charset=utf-8')
        response_content = response.content.decode()

        fieldname = 'translated'
        for code in ['de-de', 'en-us', 'es']:
            self.assertInHTML(
                (
                    f'<input'
                    f' id="id_{fieldname}__{code}"'
                    f' type="text"'
                    f' name="{fieldname}__{code}"'
                    f' value="{getattr(self.obj, fieldname)[code]}">'
                ),
                response_content,
            )
        fieldname = 'translated_multiline'
        for code in ['de-de', 'en-us', 'es']:
            self.assertInHTML(
                (
                    f'<textarea'
                    f' id="id_{fieldname}__{code}"'
                    f' name="{fieldname}__{code}">'
                    f'{getattr(self.obj, fieldname)[code]}'
                    f'</textarea>'
                ),
                response_content,
            )

        # change all translations via form
        data = {
            'initial-translated': json.dumps(self.obj.translated),
            'initial-translated_multiline': json.dumps(self.obj.translated_multiline),
        }
        for code in ['de-de', 'en-us', 'es']:
            data[f'translated__{code}'] = self.obj.translated[code].upper()
            data[f'translated_multiline__{code}'] = self.obj.translated_multiline[code].upper()
        response = self.client.post(f'/admin/test_app/translatedmodel/{self.obj.pk}/change/', data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'text/html; charset=utf-8')
        messages = response.context['messages']
        self.assertEqual(len(messages), 1)
        self.assertIn('was changed successfully', [str(m) for m in messages][0])

        self.obj.refresh_from_db()
        self.assertEqual(self.obj.translated, {'de-de': 'ZUG', 'en-us': 'TRAIN', 'es': 'TREN'})
        self.assertEqual(
            self.obj.translated_multiline,
            {
                'de-de': 'EIN ZUG IST SEHR SCHNELL.\nZÜGE KÖNNEN SCHNELLER SEIN ALS AUTOS.',
                'en-us': 'A TRAIN IS VERY FAST.\nTRAINS CAN BE FASTER THAN CARS.',
                'es': 'UN TREN ES MUY RÁPIDO.\nLOS TRENES PUEDEN SER MÁS RÁPIDOS QUE LOS AUTOMÓVILES.',
            },
        )

    def test_add(self):
        # attempt to save empty form
        response = self.client.post('/admin/test_app/translatedmodel/add/', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'text/html; charset=utf-8')
        self.assertInHTML(
            '<li>This field is required.</li>',
            response.content.decode(),
            count=1,  # error from blank TranslatedModel.translated
        )

        # save with some data
        data = {
            'initial-translated': '{}',
            'initial-translated_multiline': '{}',
            '_continue': 'Save and continue editing',
        }
        for code, field in product(['de-de', 'en-us', 'es'], ['translated', 'translated_multiline']):
            expr = f'{field}__{code}'
            data[expr] = expr
        response = self.client.post('/admin/test_app/translatedmodel/add/', data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'text/html; charset=utf-8')
        messages = response.context['messages']
        self.assertEqual(len(messages), 1)
        self.assertIn('was added successfully', [str(m) for m in messages][0])

        # was persisted?
        id_ = re.search('[0-9]+', response.request['PATH_INFO']).group()
        obj = TranslatedModel.objects.get(id=int(id_))
        self.assertEqual(
            obj.translated,
            {
                'de-de': 'translated__de-de',
                'en-us': 'translated__en-us',
                'es': 'translated__es',
            },
        )
        self.assertEqual(
            obj.translated_multiline,
            {
                'de-de': 'translated_multiline__de-de',
                'en-us': 'translated_multiline__en-us',
                'es': 'translated_multiline__es',
            },
        )
