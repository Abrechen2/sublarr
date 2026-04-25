// Mirror of backend services/inheritance_resolver.py INHERITABLE_FIELDS.
// Used by ScopeDetail to render rows in stable order, and by OverrideWidget
// to pick the correct widget variant per field type.

export type FieldType =
  | 'boolean'
  | 'enum'
  | 'language'
  | 'language_array'
  | 'string_array'
  | 'integer'
  | 'string'

export interface InheritanceField {
  readonly key: string
  readonly type: FieldType
  readonly labelKey: string  // i18n key
  readonly options?: readonly string[]  // for enum
}

export const INHERITANCE_FIELDS: readonly InheritanceField[] = [
  { key: 'cleanup_foreign_tracks', type: 'boolean', labelKey: 'profiles_overrides.field.cleanup_foreign_tracks' },
  { key: 'forced_preference', type: 'enum', labelKey: 'profiles_overrides.field.forced_preference',
    options: ['include', 'prefer', 'exclude', 'only', 'disabled', 'separate', 'auto'] },
  { key: 'hi_preference', type: 'enum', labelKey: 'profiles_overrides.field.hi_preference',
    options: ['include', 'prefer', 'exclude', 'only'] },
  { key: 'forced_scoring', type: 'enum', labelKey: 'profiles_overrides.field.forced_scoring',
    options: ['include', 'prefer', 'exclude', 'only'] },
  { key: 'target_languages', type: 'language_array', labelKey: 'profiles_overrides.field.target_languages' },
  { key: 'cutoff_language', type: 'language', labelKey: 'profiles_overrides.field.cutoff_language' },
  { key: 'must_contain', type: 'string_array', labelKey: 'profiles_overrides.field.must_contain' },
  { key: 'must_not_contain', type: 'string_array', labelKey: 'profiles_overrides.field.must_not_contain' },
  { key: 'audio_exclude_languages', type: 'language_array', labelKey: 'profiles_overrides.field.audio_exclude_languages' },
  { key: 'preferred_audio_track_index', type: 'integer', labelKey: 'profiles_overrides.field.preferred_audio_track_index' },
  { key: 'priority_override', type: 'string', labelKey: 'profiles_overrides.field.priority_override' },
  { key: 'min_attempts_per_day', type: 'integer', labelKey: 'profiles_overrides.field.min_attempts_per_day' },
] as const
