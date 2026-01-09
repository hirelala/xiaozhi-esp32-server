

## Config once in local env
> [Document](https://docs.livekit.io/agents/ops/deployment/)

First, clone this project, then:
```bash
cd livekit_agent

# auth your device, the device name can be any
lk cloud auth

# check existing project
lk project list

# create a new project on Livekit dashaboard


# create agent, it will read .env.local to config the env vars
lk agent create

# Re-deploy
lk agent deploy
```

## Stripe local
```bash
stripe listen --forward-to localhost:3000/api/subscription/webhook
```


