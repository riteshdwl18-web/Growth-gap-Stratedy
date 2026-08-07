import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'

import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { aliases, mdi } from 'vuetify/iconsets/mdi'

export const vuetify = createVuetify({
  components,
  directives,
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: {
      mdi,
    },
  },
  theme: {
    defaultTheme: 'growthGapTheme',
    themes: {
      growthGapTheme: {
        dark: false,
        colors: {
          background: '#eef1f6',
          surface: '#ffffff',
          'surface-variant': '#eef0f4',
          primary: '#2563eb',
          'primary-darken-1': '#1d4ed8',
          secondary: '#475569',
          success: '#16803d',
          warning: '#b45309',
          error: '#dc2626',
          info: '#2563eb',
          'on-surface': '#0f172a',
        },
      },
    },
  },
  defaults: {
    VBtn: {
      rounded: 'md',
      color: 'primary',
      variant: 'flat',
    },
    VCard: {
      rounded: 'lg',
      elevation: 0,
    },
    VTextField: {
      variant: 'outlined',
      density: 'comfortable',
    },
    VSelect: {
      variant: 'outlined',
      density: 'comfortable',
    },
  },
})
