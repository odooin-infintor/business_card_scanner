/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useRef, onWillUnmount } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class BCSImageField extends Component {
    static template = "business_card_scanner.BCSImageField";
    static props = { ...standardFieldProps };

    setup() {
        this.fileInputRef = useRef("bcsFileInput");
        this.videoRef    = useRef("bcsVideo");
        this.canvasRef   = useRef("bcsCanvas");
        this._modalEl    = null;
        this._stream     = null;   // ← instance-scoped, no global collision

        onWillUnmount(() => {
            this.stopCamera();
            this._destroyModal();
        });
    }

    // ── Modal ─────────────────────────────────────────────────────────
    _ensureModal() {
        if (this._modalEl) return;

        const modal = document.createElement("div");
        modal.className = "bcs_camera_modal_teleport";
        modal.innerHTML = `
            <div class="bcs_cmt_backdrop"></div>
            <div class="bcs_cmt_content">
                <video class="bcs_cmt_video" autoplay playsinline muted></video>
                <canvas class="bcs_cmt_canvas" style="display:none"></canvas>
                <div class="bcs_cmt_actions">
                    <button class="bcs_cmt_btn_capture">
                        <span class="bcs_cmt_dot"></span> Capture
                    </button>
                    <button class="bcs_cmt_btn_cancel">✕ Cancel</button>
                </div>
            </div>
        `;

        modal.querySelector(".bcs_cmt_backdrop")
             .addEventListener("click", () => this.stopCamera());
        modal.querySelector(".bcs_cmt_btn_capture")
             .addEventListener("click", (e) => { e.stopPropagation(); this.capturePhoto(); });
        modal.querySelector(".bcs_cmt_btn_cancel")
             .addEventListener("click",  (e) => { e.stopPropagation(); this.stopCamera(); });

        document.body.appendChild(modal);
        this._modalEl = modal;
    }

    _destroyModal() {
        if (this._modalEl) {
            this._modalEl.remove();
            this._modalEl = null;
        }
    }

    // ── Image helpers ─────────────────────────────────────────────────
    get imageSrc() {
        const value = this.props.record.data[this.props.name];
        if (!value) return false;
        if (typeof value === "string" && value.startsWith("data:")) return value;
        const looksLikeBinSize =
            typeof value === "string" && value.length < 20 && /[\s.]/.test(value);
        if (!looksLikeBinSize && typeof value === "string")
            return `data:image/png;base64,${value}`;
        const recordId = this.props.record.resId || this.props.record.data.id;
        const model    = this.props.record.resModel;
        const field    = this.props.name;
        if (recordId && model)
            return `/web/image/${model}/${recordId}/${field}?unique=${Date.now()}`;
        return false;
    }

    get isReadonly() { return this.props.readonly; }

    // ── Upload ────────────────────────────────────────────────────────
    triggerFileSelect() { this.fileInputRef.el?.click(); }

    onFileChange(ev) {
        const file = ev.target.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
            const base64 = String(reader.result).split(",")[1];
            this.props.record.update({ [this.props.name]: base64 });
        };
        reader.onerror = () => alert("Could not read the selected file.");
        reader.readAsDataURL(file);
        ev.target.value = "";
    }

    clearImage() { this.props.record.update({ [this.props.name]: false }); }

    // ── Camera ────────────────────────────────────────────────────────
    async openCamera() {
        this._ensureModal();
        const video = this._modalEl.querySelector(".bcs_cmt_video");

        try {
            this._stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } },
            });
            video.srcObject = this._stream;
            this._modalEl.style.display = "flex";
            document.body.style.overflow = "hidden";
        } catch (err) {
            console.error("BCS Camera error:", err);
            alert("Could not access camera. Please use file upload instead.");
        }
    }

    stopCamera() {
        // Guard: modal may already be gone
        if (!this._modalEl) {
            this._releaseStream();
            return;
        }
        this._modalEl.style.display = "none";
        document.body.style.overflow = "";
        const video = this._modalEl.querySelector(".bcs_cmt_video");
        if (video) video.srcObject = null;
        this._releaseStream();
    }

    _releaseStream() {
        if (this._stream) {
            this._stream.getTracks().forEach((t) => t.stop());
            this._stream = null;
        }
    }

    capturePhoto() {
        const video  = this._modalEl?.querySelector(".bcs_cmt_video");
        const canvas = this._modalEl?.querySelector(".bcs_cmt_canvas");
        if (!video || !canvas) return;

        canvas.width  = video.videoWidth  || 640;
        canvas.height = video.videoHeight || 480;
        canvas.getContext("2d").drawImage(video, 0, 0);

        const base64 = canvas.toDataURL("image/jpeg", 0.92).split(",")[1];
        this.props.record.update({ [this.props.name]: base64 });
        this.stopCamera();
    }
}

export const bcsImageField = {
    component: BCSImageField,
    supportedTypes: ["binary"],
    displayName: "Business Card Image (upload + camera)",
};

registry.category("fields").add("bcs_image", bcsImageField);