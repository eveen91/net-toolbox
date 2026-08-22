import React, { useState, useEffect } from "react";
import { listDevices, addDevice, deleteDevice } from "./api.js";

export default function InventoryTab() {
  const [devices, setDevices] = useState([]);
  const [formValues, setFormValues] = useState({
    name: "",
    mgmtIp: "",
    vendor: "",
    model: "",
    osVersion: "",
    deviceType: "",
  });

  const fetchDevices = async () => {
    const data = await listDevices();
    setDevices(data);
  };

  useEffect(() => {
    fetchDevices();
  }, []);

  const handleChange = (e) => {
    setFormValues({ ...formValues, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    await addDevice(formValues);
    await fetchDevices();
    setFormValues({
      name: "",
      mgmtIp: "",
      vendor: "",
      model: "",
      osVersion: "",
      deviceType: "",
    });
  };

  const handleDelete = async (id) => {
    await deleteDevice(id);
    await fetchDevices();
  };

  return (
    <div className="tool-layout">
      <div className="tool-panel">
        <form onSubmit={handleSubmit}>
          <div className="tool-field">
            <div className="tool-label">Name</div>
            <input
              className="tool-input"
              name="name"
              value={formValues.name}
              onChange={handleChange}
            />
          </div>
          <div className="tool-field">
            <div className="tool-label">Management IP</div>
            <input
              className="tool-input"
              name="mgmtIp"
              value={formValues.mgmtIp}
              onChange={handleChange}
            />
          </div>
          <div className="tool-field">
            <div className="tool-label">Vendor</div>
            <input
              className="tool-input"
              name="vendor"
              value={formValues.vendor}
              onChange={handleChange}
            />
          </div>
          <div className="tool-field">
            <div className="tool-label">Model</div>
            <input
              className="tool-input"
              name="model"
              value={formValues.model}
              onChange={handleChange}
            />
          </div>
          <div className="tool-field">
            <div className="tool-label">OS Version</div>
            <input
              className="tool-input"
              name="osVersion"
              value={formValues.osVersion}
              onChange={handleChange}
            />
          </div>
          <div className="tool-field">
            <div className="tool-label">Device Type</div>
            <input
              className="tool-input"
              name="deviceType"
              value={formValues.deviceType}
              onChange={handleChange}
            />
          </div>
          <div className="tool-actions">
            <button className="tool-btn" type="submit">
              Add Device
            </button>
          </div>
        </form>
      </div>

      <div className="tool-panel">
        <div className="tool-table-wrap">
          <table className="tool-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Management IP</th>
                <th>Vendor</th>
                <th>Model</th>
                <th>Device Type</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((device) => (
                <tr key={device.id}>
                  <td>{device.name}</td>
                  <td>{device.mgmtIp}</td>
                  <td>{device.vendor}</td>
                  <td>{device.model}</td>
                  <td>{device.deviceType}</td>
                  <td>
                    <button
                      className="tool-btn"
                      onClick={() => handleDelete(device.id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
