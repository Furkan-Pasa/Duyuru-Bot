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
      error_file: "./logs/pm2/error.log",
      out_file: "/dev/null",
      log_file: "/dev/null",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      env: {
        NODE_ENV: "production",
      },
    },
  ],
};
