FROM node:20-slim

WORKDIR /app

COPY package*.json /app/
RUN npm install

COPY . /app/

EXPOSE 5173

# Vite requires --host to bind to 0.0.0.0 for external docker routing
CMD ["npm", "run", "dev", "--", "--host"]
