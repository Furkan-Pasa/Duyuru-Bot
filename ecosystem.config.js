module.exports = {
  apps: [
    {
      name: "duyuru-bot",
      script: "bot_main.py",
      interpreter: "./.venv/bin/python3",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "300M",
      env: {
        NODE_ENV: "production",
      },
    },
  ],
};
