import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles/main.css'
import StudioIcon from './components/StudioIcon.vue'

const app = createApp(App)
app.component('StudioIcon',StudioIcon)
app.use(createPinia())
app.use(router)
app.mount('#app')
