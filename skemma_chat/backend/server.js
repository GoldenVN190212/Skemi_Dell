// Skemi Chat — real-time signaling backend (Socket.IO) + attachment uploads.
// Message/friend data lives in Firebase (client-side, same as the rest of the
// app); this process only relays live events (typing, delivery, presence) and
// stores uploaded chat attachments on disk. In-folder copy of the original
// Skemma-main chat server, trimmed of legacy routes already covered by
// Skemi's own Server.py (translate-ui, ask_stream, parse_file, AI-server spawn).

import http from "http";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import express from "express";
import { Server } from "socket.io";
import cors from "cors";
import multer from "multer";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PORT = Number(process.env.SKEMMA_CHAT_PORT || process.env.PORT || 8001);

const app = express();
app.use(cors({ origin: true, credentials: true }));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.get(["/api/health", "/health"], (req, res) => res.json({ status: "healthy" }));
app.get("/status", (req, res) => res.json({ status: "online", clients: io.engine.clientsCount }));
app.get("/favicon.ico", (req, res) => res.status(204).end());

// Chat attachment uploads.
const uploadDir = path.join(__dirname, "uploads");
if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });
const storage = multer.diskStorage({
    destination: (req, file, cb) => cb(null, uploadDir),
    filename: (req, file, cb) => cb(null, `${Date.now()}_${file.originalname}`),
});
const upload = multer({ storage, limits: { fileSize: 50 * 1024 * 1024 } });
app.post("/api/upload", upload.single("file"), (req, res) => {
    if (!req.file) return res.status(400).json({ error: "No file uploaded" });
    res.json({ url: `/uploads/${req.file.filename}`, file_name: req.file.originalname, size: req.file.size });
});
app.use("/uploads", express.static(uploadDir));

const server = http.createServer(app);
const io = new Server(server, {
    cors: { origin: true, credentials: true },
    transports: ["websocket", "polling"],
});

// In-memory presence/routing only — message history is Firebase's job.
const userSockets = {};
const userPresence = {};

io.on("connection", (socket) => {
    const userId = socket.handshake.auth?.uid;
    if (!userId) return;

    userSockets[userId] = socket.id;
    userPresence[userId] = { online: true, lastSeen: Date.now() };

    socket.on("join_user_room", (data) => socket.join(`user_${data.uid}`));

    socket.on("typing", (data) => {
        const targetId = userSockets[data.receiver];
        if (targetId) io.to(targetId).emit("typing", data);
    });

    socket.on("send_message", (data) => {
        const msg = { ...data, timestamp: Date.now() };
        socket.emit("receive_message", msg);
        const targetId = userSockets[data.receiver];
        if (targetId) io.to(targetId).emit("receive_message", msg);
    });

    socket.on("disconnect", () => {
        if (userId) userPresence[userId] = { online: false, lastSeen: Date.now() };
    });
});

process.once("SIGINT", () => process.exit(0));
process.once("SIGTERM", () => process.exit(0));

server.listen(PORT, "0.0.0.0", () => {
    console.log(`[Skemi Chat] real-time backend on :${PORT}`);
});
