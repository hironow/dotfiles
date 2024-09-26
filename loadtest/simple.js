import http from 'k6/http'
import { sleep } from 'k6'

// See https://grafana.com/docs/k6/latest/using-k6/k6-options/
export const options = {
  vus: 10,
  duration: '30s',
  cloud: {
    name: 'YOUR TEST NAME',
  },
}

export default function () {
  http.get('https://test.k6.io')
  sleep(1)
}
