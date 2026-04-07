from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class FormOption(BaseModel):
    value: str
    label: str
    description: str | None = None


class BaseFormField(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    label: str
    description: str | None = None
    example: str | bool | None = None
    required: bool = False


class TextFormField(BaseFormField):
    kind: Literal['text', 'email'] = 'text'
    placeholder: str | None = None


class TextareaFormField(BaseFormField):
    kind: Literal['textarea'] = 'textarea'
    placeholder: str | None = None


class SelectFormField(BaseFormField):
    kind: Literal['select'] = 'select'
    options: list[FormOption] = Field(min_length=1)
    placeholder: str | None = None


class CheckboxFormField(BaseFormField):
    kind: Literal['checkbox'] = 'checkbox'
    description: str | None = None
    example: bool | None = None


FormField = Annotated[
    TextFormField | TextareaFormField | SelectFormField | CheckboxFormField,
    Field(discriminator='kind'),
]


FORM_FIELD_ADAPTER = TypeAdapter(FormField)


class HumanFormDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: str
    description: str
    submit_label: str = Field(default='Submit', alias='submitLabel')
    cancel_label: str = Field(default='Cancel', alias='cancelLabel')
    fields: list[FormField] = Field(min_length=1)

    def ui_payload(self) -> dict[str, object]:
        return {
            'title': self.title,
            'description': self.description,
            'submitLabel': self.submit_label,
            'cancelLabel': self.cancel_label,
            'fields': [field.model_dump(mode='json') for field in self.fields],
            'schema': self.model_json_schema(mode='serialization'),
        }


def build_onboarding_preferences_form(*, title: str, description: str) -> HumanFormDefinition:
    return HumanFormDefinition(
        title=title,
        description=description,
        submitLabel='Send preferences',
        cancelLabel='Cancel',
        fields=[
            TextFormField(
                kind='text',
                name='name',
                label='Full name',
                description='Name to use during onboarding and support follow-ups.',
                example='Daniel Ortiz',
                placeholder='Daniel Ortiz',
                required=True,
            ),
            TextFormField(
                kind='email',
                name='email',
                label='Work email',
                description='Main email for onboarding updates.',
                example='daniel@example.com',
                placeholder='name@example.com',
                required=True,
            ),
            TextFormField(
                kind='text',
                name='company',
                label='Company',
                description='Company or team name.',
                example='Acme Studio',
                placeholder='Acme Studio',
                required=True,
            ),
            SelectFormField(
                kind='select',
                name='role',
                label='Role',
                description='Primary role for this workspace.',
                example='product',
                required=True,
                options=[
                    FormOption(value='engineering', label='Engineering'),
                    FormOption(value='product', label='Product'),
                    FormOption(value='operations', label='Operations'),
                    FormOption(value='support', label='Support'),
                ],
            ),
            CheckboxFormField(
                kind='checkbox',
                name='marketing_consent',
                label='Allow onboarding tips by email',
                description='Receive occasional onboarding tips and product education emails.',
                example=True,
                required=False,
            ),
            SelectFormField(
                kind='select',
                name='preferred_channel',
                label='Preferred contact channel',
                description='Where onboarding updates should be sent first.',
                example='email',
                required=True,
                options=[
                    FormOption(value='email', label='Email'),
                    FormOption(value='slack', label='Slack'),
                    FormOption(value='phone', label='Phone'),
                ],
            ),
            SelectFormField(
                kind='select',
                name='timezone',
                label='Time zone',
                description='Used to schedule onboarding sessions.',
                example='utc_plus_1',
                required=True,
                options=[
                    FormOption(value='utc_minus_8', label='UTC -8'),
                    FormOption(value='utc', label='UTC'),
                    FormOption(value='utc_plus_1', label='UTC +1'),
                    FormOption(value='utc_plus_5_30', label='UTC +5:30'),
                ],
            ),
            SelectFormField(
                kind='select',
                name='product_interest',
                label='Primary product interest',
                description='The area the customer wants to explore first.',
                example='automation',
                required=True,
                options=[
                    FormOption(value='automation', label='Automation'),
                    FormOption(value='analytics', label='Analytics'),
                    FormOption(value='collaboration', label='Collaboration'),
                ],
            ),
            TextareaFormField(
                kind='textarea',
                name='accessibility_needs',
                label='Accessibility needs',
                description='Optional accommodations or preferences for calls and docs.',
                example='Please use captions during video calls.',
                placeholder='Share any accessibility preferences',
                required=False,
            ),
        ],
    )
