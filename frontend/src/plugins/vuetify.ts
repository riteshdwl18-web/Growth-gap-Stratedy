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
          background: '#f4f7fb',
          surface: '#ffffff',
          primary: '#0f3b82',
          secondary: '#0d9488',
          success: '#2e7d32',
          warning: '#b26a00',
          error: '#b42318',
          info: '#1d4ed8',
        },
      },
    },
  },
  defaults: {
    VBtn: {
      rounded: 'lg',
      color: 'primary',
      variant: 'flat',
    },
    VCard: {
      rounded: 'xl',
      elevation: 2,
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
