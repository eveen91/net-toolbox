export function isValidIpv4(value) {
  const parts = value.trim().split(".");
  return parts.length === 4 && parts.every((part) => /^\d+$/.test(part) && Number(part) >= 0 && Number(part) <= 255);
}

export function compareIpv4(left, right) {
  return left.split(".").reduce((total, part) => total * 256 + Number(part), 0) - right.split(".").reduce((total, part) => total * 256 + Number(part), 0);
}

export function activeReservationForIp(reservations, ip) {
  return reservations.find((reservation) => reservation.status === "active" && compareIpv4(reservation.start_ip, ip) <= 0 && compareIpv4(ip, reservation.end_ip) <= 0) || null;
}
