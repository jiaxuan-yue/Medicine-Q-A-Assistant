import React, { useState } from 'react';
import { Upload, Button, Image, message } from 'antd';
import { PictureOutlined, DeleteOutlined } from '@ant-design/icons';
import type { RcFile } from 'antd/es/upload';

interface UploadImagePanelProps {
  onImageSelected: (file: File) => void;
}

const ACCEPT_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_SIZE_MB = 10;

const UploadImagePanel: React.FC<UploadImagePanelProps> = ({ onImageSelected }) => {
  const [preview, setPreview] = useState<string | null>(null);

  const beforeUpload = (file: RcFile) => {
    if (!ACCEPT_TYPES.includes(file.type)) {
      message.error('仅支持 JPG、PNG、WebP 格式的图片');
      return Upload.LIST_IGNORE;
    }
    if (file.size / 1024 / 1024 > MAX_SIZE_MB) {
      message.error(`图片大小不能超过 ${MAX_SIZE_MB}MB`);
      return Upload.LIST_IGNORE;
    }

    const url = URL.createObjectURL(file);
    setPreview(url);
    onImageSelected(file);

    // Prevent auto upload
    return false;
  };

  const handleRemove = () => {
    if (preview) {
      URL.revokeObjectURL(preview);
    }
    setPreview(null);
  };

  return (
    <div className="upload-image-panel" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {preview ? (
        <div style={{ position: 'relative', display: 'inline-block' }}>
          <Image
            src={preview}
            alt="预览"
            width={64}
            height={64}
            style={{ objectFit: 'cover', borderRadius: 6 }}
            preview={{ mask: '查看' }}
          />
          <Button
            type="text"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={handleRemove}
            style={{
              position: 'absolute',
              top: -8,
              right: -8,
              background: '#fff',
              borderRadius: '50%',
              boxShadow: '0 1px 4px rgba(0,0,0,0.15)',
              padding: 0,
              width: 20,
              height: 20,
              minWidth: 20,
            }}
          />
        </div>
      ) : (
        <Upload
          accept=".jpg,.jpeg,.png,.webp"
          showUploadList={false}
          beforeUpload={beforeUpload}
        >
          <Button
            type="text"
            icon={<PictureOutlined />}
            title="上传图片"
          />
        </Upload>
      )}
    </div>
  );
};

export default UploadImagePanel;
