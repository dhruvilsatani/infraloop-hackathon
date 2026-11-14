FROM node:22-slim

WORKDIR /app

# Dependencies are installed inside the image, so no Node.js is needed on the host machine.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 4200
CMD ["npx", "ng", "serve", "--host", "0.0.0.0", "--port", "4200", "--poll", "2000"]
