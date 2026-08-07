import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './router'
import { vuetify } from './plugins/vuetify'

const app = createApp(App).use(router).use(vuetify)

// Wait for the router's initial navigation (including its async auth guard) to
// resolve before mounting, so App.vue's onMounted doesn't race the guard's own
// auth check and fire a duplicate /api/auth/me request on cold page loads.
router.isReady().then(() => {
  app.mount('#app')
})
