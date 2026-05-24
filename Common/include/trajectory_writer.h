#ifndef TRAJECTORY_WRITER_H
#define TRAJECTORY_WRITER_H

#include "body.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <ios>
#include <stdexcept>
#include <string>
#include <vector>

enum class TrajectoryFormat {
    Csv,
    Binary
};

inline std::string normalizeTrajectoryFormat(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return value;
}

inline TrajectoryFormat parseTrajectoryFormat(const std::string& value) {
    const std::string format = normalizeTrajectoryFormat(value);
    if (format == "csv") {
        return TrajectoryFormat::Csv;
    }
    if (format == "binary" || format == "bin") {
        return TrajectoryFormat::Binary;
    }
    throw std::invalid_argument("Unknown trajectory format '" + value + "'. Use csv or binary.");
}

inline std::string trajectoryFormatToString(TrajectoryFormat format) {
    return format == TrajectoryFormat::Csv ? "csv" : "binary";
}

class TrajectoryWriter {
public:
    TrajectoryWriter() = default;

    explicit TrajectoryWriter(const std::string& path,
                              TrajectoryFormat format = TrajectoryFormat::Csv) {
        open(path, format);
    }

    ~TrajectoryWriter() {
        close();
    }

    void open(const std::string& path,
              TrajectoryFormat format = TrajectoryFormat::Csv) {
        if (path.empty()) {
            return;
        }

        const std::filesystem::path output_path(path);
        const auto parent = output_path.parent_path();
        if (!parent.empty()) {
            std::filesystem::create_directories(parent);
        }

        format_ = format;
        stream_buffer_.assign(kStreamBufferBytes, '\0');
        file_.rdbuf()->pubsetbuf(stream_buffer_.data(), static_cast<std::streamsize>(stream_buffer_.size()));

        std::ios::openmode mode = std::ios::out;
        if (format_ == TrajectoryFormat::Binary) {
            mode |= std::ios::binary;
        }
        file_.open(output_path, mode);
        if (!file_) {
            throw std::runtime_error("Failed to open trajectory output file: " + path);
        }

        if (format_ == TrajectoryFormat::Csv) {
            file_ << std::setprecision(17);
            file_ << "step,time_s,body,mass,x,y,z,vx,vy,vz,ax,ay,az\n";
        } else {
            writeBinaryFileHeader();
        }
    }

    bool enabled() const {
        return file_.is_open();
    }

    void close() {
        if (file_.is_open()) {
            file_.close();
        }
    }

    TrajectoryFormat format() const {
        return format_;
    }

    void write(size_t step, double time_s, const std::vector<Body>& bodies) {
        if (!enabled()) {
            return;
        }

        if (format_ == TrajectoryFormat::Binary) {
            resizeScratch(bodies.size());
            for (size_t i = 0; i < bodies.size(); ++i) {
                const Body& body = bodies[i];
                scratch_mass_[i] = body.mass;
                scratch_pos_x_[i] = body.position.x;
                scratch_pos_y_[i] = body.position.y;
                scratch_pos_z_[i] = body.position.z;
                scratch_vel_x_[i] = body.velocity.x;
                scratch_vel_y_[i] = body.velocity.y;
                scratch_vel_z_[i] = body.velocity.z;
                scratch_acc_x_[i] = body.acceleration.x;
                scratch_acc_y_[i] = body.acceleration.y;
                scratch_acc_z_[i] = body.acceleration.z;
            }
            writeBinaryArrays(
                step,
                time_s,
                scratch_mass_,
                scratch_pos_x_,
                scratch_pos_y_,
                scratch_pos_z_,
                scratch_vel_x_,
                scratch_vel_y_,
                scratch_vel_z_,
                scratch_acc_x_,
                scratch_acc_y_,
                scratch_acc_z_
            );
            return;
        }

        for (size_t i = 0; i < bodies.size(); ++i) {
            const Body& body = bodies[i];
            writeRow(
                step,
                time_s,
                i,
                body.mass,
                body.position.x,
                body.position.y,
                body.position.z,
                body.velocity.x,
                body.velocity.y,
                body.velocity.z,
                body.acceleration.x,
                body.acceleration.y,
                body.acceleration.z
            );
        }
    }

    void writeArrays(size_t step,
                     double time_s,
                     const std::vector<double>& mass,
                     const std::vector<double>& pos_x,
                     const std::vector<double>& pos_y,
                     const std::vector<double>& pos_z,
                     const std::vector<double>& vel_x,
                     const std::vector<double>& vel_y,
                     const std::vector<double>& vel_z,
                     const std::vector<double>& acc_x,
                     const std::vector<double>& acc_y,
                     const std::vector<double>& acc_z) {
        if (!enabled()) {
            return;
        }

        if (format_ == TrajectoryFormat::Binary) {
            writeBinaryArrays(
                step,
                time_s,
                mass,
                pos_x,
                pos_y,
                pos_z,
                vel_x,
                vel_y,
                vel_z,
                acc_x,
                acc_y,
                acc_z
            );
            return;
        }

        const size_t n = mass.size();
        for (size_t i = 0; i < n; ++i) {
            writeRow(
                step,
                time_s,
                i,
                mass[i],
                pos_x[i],
                pos_y[i],
                pos_z[i],
                vel_x[i],
                vel_y[i],
                vel_z[i],
                acc_x[i],
                acc_y[i],
                acc_z[i]
            );
        }
    }

private:
    static constexpr size_t kStreamBufferBytes = 4 * 1024 * 1024;

    std::vector<char> stream_buffer_;
    std::ofstream file_;
    TrajectoryFormat format_ = TrajectoryFormat::Csv;
    std::vector<double> scratch_mass_;
    std::vector<double> scratch_pos_x_;
    std::vector<double> scratch_pos_y_;
    std::vector<double> scratch_pos_z_;
    std::vector<double> scratch_vel_x_;
    std::vector<double> scratch_vel_y_;
    std::vector<double> scratch_vel_z_;
    std::vector<double> scratch_acc_x_;
    std::vector<double> scratch_acc_y_;
    std::vector<double> scratch_acc_z_;

    void resizeScratch(size_t n) {
        scratch_mass_.resize(n);
        scratch_pos_x_.resize(n);
        scratch_pos_y_.resize(n);
        scratch_pos_z_.resize(n);
        scratch_vel_x_.resize(n);
        scratch_vel_y_.resize(n);
        scratch_vel_z_.resize(n);
        scratch_acc_x_.resize(n);
        scratch_acc_y_.resize(n);
        scratch_acc_z_.resize(n);
    }

    template <typename T>
    void writePod(const T& value) {
        file_.write(reinterpret_cast<const char*>(&value), sizeof(T));
    }

    void writeBytes(const char* data, size_t bytes) {
        file_.write(data, static_cast<std::streamsize>(bytes));
    }

    void writeDoubleArray(const std::vector<double>& values) {
        if (!values.empty()) {
            writeBytes(reinterpret_cast<const char*>(values.data()), values.size() * sizeof(double));
        }
    }

    void writeBinaryFileHeader() {
        const char magic[16] = {'N', 'B', 'O', 'D', 'Y', 'T', 'R', 'J', 'B', 'I', 'N', '1', '\0', '\0', '\0', '\0'};
        const uint32_t version = 1;
        const uint32_t endian_marker = 0x01020304u;
        const uint32_t scalar_size = sizeof(double);
        const uint32_t arrays_per_frame = 10;
        const uint32_t layout = 1; // 1 = structure of arrays: mass,x,y,z,vx,vy,vz,ax,ay,az.

        writeBytes(magic, sizeof(magic));
        writePod(version);
        writePod(endian_marker);
        writePod(scalar_size);
        writePod(arrays_per_frame);
        writePod(layout);
    }

    void validateArraySizes(size_t n,
                            const std::vector<double>& pos_x,
                            const std::vector<double>& pos_y,
                            const std::vector<double>& pos_z,
                            const std::vector<double>& vel_x,
                            const std::vector<double>& vel_y,
                            const std::vector<double>& vel_z,
                            const std::vector<double>& acc_x,
                            const std::vector<double>& acc_y,
                            const std::vector<double>& acc_z) {
        if (pos_x.size() != n || pos_y.size() != n || pos_z.size() != n ||
            vel_x.size() != n || vel_y.size() != n || vel_z.size() != n ||
            acc_x.size() != n || acc_y.size() != n || acc_z.size() != n) {
            throw std::runtime_error("Trajectory arrays have mismatched sizes.");
        }
    }

    void writeBinaryArrays(size_t step,
                           double time_s,
                           const std::vector<double>& mass,
                           const std::vector<double>& pos_x,
                           const std::vector<double>& pos_y,
                           const std::vector<double>& pos_z,
                           const std::vector<double>& vel_x,
                           const std::vector<double>& vel_y,
                           const std::vector<double>& vel_z,
                           const std::vector<double>& acc_x,
                           const std::vector<double>& acc_y,
                           const std::vector<double>& acc_z) {
        const size_t n = mass.size();
        validateArraySizes(n, pos_x, pos_y, pos_z, vel_x, vel_y, vel_z, acc_x, acc_y, acc_z);

        const char frame_magic[8] = {'F', 'R', 'A', 'M', 'E', '0', '0', '1'};
        const uint64_t step_u64 = static_cast<uint64_t>(step);
        const uint64_t n_u64 = static_cast<uint64_t>(n);

        writeBytes(frame_magic, sizeof(frame_magic));
        writePod(step_u64);
        writePod(time_s);
        writePod(n_u64);
        writeDoubleArray(mass);
        writeDoubleArray(pos_x);
        writeDoubleArray(pos_y);
        writeDoubleArray(pos_z);
        writeDoubleArray(vel_x);
        writeDoubleArray(vel_y);
        writeDoubleArray(vel_z);
        writeDoubleArray(acc_x);
        writeDoubleArray(acc_y);
        writeDoubleArray(acc_z);
    }

    void writeRow(size_t step,
                  double time_s,
                  size_t body_index,
                  double mass,
                  double x,
                  double y,
                  double z,
                  double vx,
                  double vy,
                  double vz,
                  double ax,
                  double ay,
                  double az) {
        file_ << step << ','
              << time_s << ','
              << body_index << ','
              << mass << ','
              << x << ','
              << y << ','
              << z << ','
              << vx << ','
              << vy << ','
              << vz << ','
              << ax << ','
              << ay << ','
              << az << '\n';
    }
};

#endif // TRAJECTORY_WRITER_H
